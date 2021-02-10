use std::env;
use std::fs::{metadata, File, OpenOptions, remove_file};
use std::io::{prelude::*, ErrorKind::UnexpectedEof, Read, SeekFrom, Write};

extern crate rust_codec;
use rust_codec::codec;

const COMPRESSED: &str = "/tmp/compressed_headers.dat";
const DECOMPRESSED: &str = "/tmp/decompressed_headers.dat";

// Read headers from input, compress them using Codec and write them to output.
fn compress_headers<R: Read, W: Write>(
    input: &mut R,
    output: &mut W,
    codec: &mut codec::Codec,
) -> usize {
    let mut total_bytes: usize = 0;
    loop {
        match codec.compress(input, output) {
            Ok(bytes_written) => total_bytes += bytes_written,
            Err(e) => match e.kind() {
                UnexpectedEof => {
                    print!("Reached EOF\n");
                    return total_bytes;
                }
                _ => {
                    panic!("Unexpected error reading uncompressed header");
                }
            },
        }
    }
}

// Read compressed headers from input, decompress them using Codec and write
// decompressed to output.
fn decompress_headers<R: Read, W: Write>(
    input: &mut R,
    output: &mut W,
    codec: &mut codec::Codec,
) -> () {
    loop {
        match codec.decompress(input, output) {
            Ok(_) => (),
            Err(e) => match e.kind() {
                UnexpectedEof => {
                    print!("Reached EOF");
                    return ()
                }
                _ => {
                    panic!("Unexpected error reading compressed header");
                }
            },
        }
    }
}

// Takes a vector of objects implementing Seek and rewinds them
// Rewinds all the readers in the vector to the beginning
fn rewind_cursors<S: Seek>(readers: &mut Vec<S>) -> () {
    for reader in readers {
        match reader.seek(SeekFrom::Start(0)) {
            // TODO: handle these errors properly!
            Ok(_) => (),
            Err(_) => (),
        };
    }
}

// Takes two files and compares them
// https://docs.rs/file_diff/1.0.0/src/file_diff/lib.rs.html#7-106
pub fn diff_files(f1: &mut File, f2: &mut File) -> bool {
    let buff1: &mut [u8] = &mut [0; 1024];
    let buff2: &mut [u8] = &mut [0; 1024];
    loop {
        match f1.read(buff1) {
            Err(_) => return false,
            Ok(f1_read_len) => match f2.read(buff2) {
                Err(_) => return false,
                Ok(f2_read_len) => {
                    if f1_read_len != f2_read_len {
                        return false;
                    }
                    if f1_read_len == 0 {
                        return true;
                    }
                    if &buff1[0..f1_read_len] != &buff2[0..f2_read_len] {
                        return false;
                    }
                }
            },
        }
    }
}

fn diff_files2(f1: &mut File, f2: &mut File) -> () {
    let buff1: &mut [u8] = &mut [0; 80];
    let buff2: &mut [u8] = &mut [0; 80];
    let mut count: usize = 1;
    loop {
        match f1.read_exact(buff1) {
            Err(_) => println!("error reading from f1 at count: {}", count),
            Ok(_) => match f2.read_exact(buff2) {
                Err(_) => println!("error reading from f2 at count: {}", count),
                Ok(_) => {
                    if &buff1[..] != &buff2[..] {
						let mut i:usize = 0;
						while i < 80 {
                            if buff1[i] != buff2[i] {
                                println!("mismatch in header {} at byte {}", count, i);
                            }
                            i += 1;
                        }
                    }
                }
            },
        }
        count += 1;

    }

}

fn main() -> std::io::Result<()> {
    let original: String = env::args()
        .nth(1)
        .expect("Pass filepath to uncompressed binary headers file");
	let _len = metadata(&original).unwrap().len();
    let _count = _len / 80;
    println!(
        "Total size of {} uncompressed headers: {} B",
        _count,
        _len,
    );
    let mut codec = codec::Codec::new();
    let mut original: File = OpenOptions::new().read(true).open(original)?;
    match remove_file(COMPRESSED) {
        Ok(_) => (),
        Err(e) => println!("Error removing file: {} : {:?}", COMPRESSED, e),
    }
    let mut compressed: File = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .open(COMPRESSED)?;
    match remove_file(DECOMPRESSED) {
        Ok(_) => (),
        Err(e) => println!("Error removing file: {} : {:?}", DECOMPRESSED, e),
    }
    let mut decompressed: File = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .open(DECOMPRESSED)?;

    // Test compression
    let compressed_bytes: usize = compress_headers(&mut original, &mut compressed, &mut codec);
    println!("Total size of compressed headers:   {} B", compressed_bytes);
    rewind_cursors(&mut vec![&original, &compressed]);

    // Test decompression
    decompress_headers(&mut compressed, &mut decompressed, &mut codec);
    rewind_cursors(&mut vec![&original, &decompressed]);

    // Compare original to decompressed
    diff_files(&mut original, &mut decompressed);
    // diff_files2(&mut original, &mut decompressed);
    // println!("Decompressed matches original: {}", same);

    Ok(())
}
