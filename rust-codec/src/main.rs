use std::convert::TryInto;
use std::fs::File;
use std::io::prelude::*;
use std::io::BufReader;
use std::io::ErrorKind::UnexpectedEof;
mod macros;
use sha2::{Digest, Sha256};

const HEADER_LEN: usize = 80;

const MASK_VERSION: u8 = 7 << 5;
const MASK_PREV_BLOCK_HASH: u8 = 1 << 4;
const MASK_TIME: u8 = 1 << 3;
const MASK_NBITS: u8 = 1 << 2;
const MASK_END: u8 = 1 << 1;

const PATH: &str = "/Users/will/src/compressed-block-headers/uncompressed_headers.dat";

#[derive(Clone, Debug)]
struct BlockHeader {
    version: i32,
    prev_block_hash: [u8; 32],
    merkle_root: [u8; 32],
    time: u32,
    n_bits: u32,
    nonce: u32,
}

impl BlockHeader {
    // Takes an 80 byte array
    fn from_bytes(&header: &[u8; 80]) -> BlockHeader {
        BlockHeader {
            version: i32_from_be_bytes!(header[0..4]),
            prev_block_hash: u8_32_from_bytes!(header[4..36]),
            merkle_root: u8_32_from_bytes!(header[36..68]),
            time: u32_from_le_bytes!(header[68..72]),
            n_bits: u32_from_le_bytes!(header[72..76]),
            nonce: u32_from_le_bytes!(header[76..80]),
        }
    }

    fn hash(&self) -> [u8; 32] {
        let mut hasher = Sha256::new();
        hasher.update(&self.version.to_be_bytes());
        hasher.update(&self.prev_block_hash);
        hasher.update(&self.merkle_root);
        hasher.update(&self.time.to_le_bytes());
        hasher.update(&self.n_bits.to_le_bytes());
        hasher.update(&self.nonce.to_le_bytes());

        let result = hasher.finalize();
        result.into()
    }
}

struct Deque {
    queue: Vec<i32>,
}

impl Deque {
    fn insert(&mut self, value: i32) -> () {
        &self.queue.insert(0, value);
        &self.queue.truncate(7);
    }
}

struct CompressorState {
    prev_versions: Deque,
    prev_header: Option<BlockHeader>,
}

impl CompressorState {
    fn new() -> Self {
        CompressorState {
            prev_versions: Deque { queue: Vec::new() },
            prev_header: Option::None,
        }
    }
}

struct Codec {
    compressor: CompressorState,
    decompressor: CompressorState,
}

impl Codec {
    fn compress(&mut self, &header_bytes: &[u8; 80]) -> Vec<u8> {
        let header = BlockHeader::from_bytes(&header_bytes);
        // Initialise bitfield and result vector
        let mut bitfield: u8 = 0b00000000;
        let mut result: Vec<u8> = Vec::new();

        // Version
        if self
            .compressor
            .prev_versions
            .queue
            .contains(&header.version)
        {
            // Version is in previous 7 versions
            let index = &self
                .compressor
                .prev_versions
                .queue
                .iter()
                .position(|&x| x == header.version)
                .unwrap();
            bitfield = bitfield ^ ((*index as u8) << 5);
        } else {
            // This is a new distinct version
            &self.compressor.prev_versions.insert(header.version);
            bitfield = bitfield ^ MASK_VERSION;
            for byte in &header.version.to_be_bytes() {
                result.push(*byte);
            }
        }

        // Prev Block Hash
        // Only send prev_block_hash on first compression of the session
        if let None = &self.compressor.prev_header {
            bitfield = bitfield ^ MASK_PREV_BLOCK_HASH;
            for byte in &header.prev_block_hash {
                result.push(*byte);
            }
        }

        // Merkle Root
        // Always included
        for byte in &header.merkle_root {
            result.push(*byte);
        }

        // Time
        // Always include on the first of each session
        if let None = &self.compressor.prev_header {
            for byte in &header.time.to_be_bytes() {
                result.push(*byte);
            }
        } else {
            let prev_time = &self.compressor.prev_header.as_ref().unwrap().time;
            let header_time = &header.time;
            // Use i64 to avoid overflow
            let time_offset = *header_time as i64 - *prev_time as i64;
            // Bit of a messy hack to subtract two u32's
            if (i16::MIN as i64 <= time_offset) && (time_offset <= i16::MAX as i64) {
                bitfield = bitfield ^ MASK_TIME;
                let time_offset = time_offset as i16;
                for byte in &time_offset.to_le_bytes() {
                    result.push(*byte);
                }
            } else {
                for byte in &time_offset.to_le_bytes() {
                    result.push(*byte);
                }
            }
        }

        // n_bits
        if self.compressor.prev_header.is_none() {
            for byte in &header.n_bits.to_le_bytes() {
                result.push(*byte);
            }
        } else if header.n_bits == self.compressor.prev_header.as_ref().unwrap().n_bits {
            bitfield = bitfield ^ MASK_NBITS;
        } else {
            for byte in &header.n_bits.to_le_bytes() {
                result.push(*byte);
            }
        }

        // Nonce always required
        for byte in &header.nonce.to_le_bytes() {
            result.push(*byte);
        }

        // Write the bitfield
        result.insert(0, bitfield);

        // Set compressor's prev_header to header
        self.compressor.prev_header = Some(header);

        result
    }

    fn decompress(&mut self, in_stream: BufReader<u8>) -> BlockHeader {
        // let mut reader = BufReader::new(header);
        let mut header = BlockHeader {
            version: 0,
            prev_block_hash: [0; 32],
            merkle_root: [0; 32],
            time: 0,
            n_bits: 0,
            nonce: 0,
        };

        // Read the bitfield
        let mut buffer: [u8; 1] = [0; 1];
        match in_stream.buffer().read_exact(&mut buffer) {
            Ok(_) => (),
            Err(e) => {
                panic!("Can't read bitfield from stream");
            }
        }
        let bitfield = buffer[0];

        // Version
        let v_index = bitfield >> 5;
        if v_index == MASK_VERSION {
            // Version not in previous 7 distinct versions
            let mut buffer: [u8; 4] = [0; 4];
            match in_stream.buffer().read_exact(&mut buffer) {
                Ok(_) => header.version = i32_from_be_bytes!(buffer),
                Err(e) => panic!("Error reading v_index: {}", e),
            }
        } else {
            // Lookup the version from the Deque using v_index
            header.version = self.decompressor.prev_versions.queue[v_index as usize];
        }

        // Prev_block_hash
        if (bitfield & MASK_PREV_BLOCK_HASH) > 0 {
            let mut buffer: [u8; 32] = [0; 32];
            match in_stream.buffer().read_exact(&mut buffer) {
                Ok(_) => header.prev_block_hash = buffer,
                Err(e) => panic!("Error reading prev_block_hash: {}", e),
            }
        } else {
            header.prev_block_hash = self.decompressor.prev_header.as_ref().unwrap().hash();
        }

        // Merkle root
        let mut buffer: [u8; 32] = [0; 32];
        match in_stream.buffer().read_exact(&mut buffer) {
            Ok(_) => header.merkle_root = buffer,
            Err(e) => panic!("Error reading merkle_root: {}", e),
        }

        // Time
        if (bitfield & MASK_TIME) > 0 {
            let mut buffer: [u8; 2] = [0; 2];
            match in_stream.buffer().read_exact(&mut buffer) {
                Ok(_) => {
                    let time_offset = i16::from_le_bytes(buffer);
                    header.time = (self.decompressor.prev_header.as_ref().unwrap().time as i64
                        + time_offset as i64) as u32;
                }
                Err(e) => panic!("Error reading time: {}", e),
            }
        } else {
            let mut buffer: [u8; 4] = [0; 4];
            in_stream.buffer().read_exact(&mut buffer);
            header.time = u32::from_le_bytes(buffer);
        }

        // n_bits
        if (bitfield & MASK_NBITS) > 0 {
            header.n_bits = self.decompressor.prev_header.as_ref().unwrap().n_bits;
        } else {
            let mut buffer: [u8; 4] = [0; 4];
            in_stream.buffer().read_exact(&mut buffer);
            header.n_bits = u32::from_le_bytes(buffer);
        }

        // Nonce
        let mut buffer: [u8; 4] = [0; 4];
        in_stream.buffer().read_exact(&mut buffer);
        header.nonce = u32::from_le_bytes(buffer);

        header
    }
}

fn main() -> std::io::Result<()> {
    let mut codec = Codec {
        compressor: CompressorState::new(),
        decompressor: CompressorState::new(),
    };

    let mut buffer = [0; HEADER_LEN];
    let mut total_raw = 0;
    let mut total_compressed = 0;

    let mut f = File::open(PATH)?;
    let mut reader = BufReader::new(f);
    loop {
        match reader.read_exact(&mut buffer) {
            Ok(_) => {
                total_raw += 80;
                let compressed_header = codec.compress(&buffer);
                total_compressed += compressed_header.len();
            }
            Err(e) => match e.kind() {
                UnexpectedEof => {
                    print!("Reached EOF\n");
                    break;
                }
                _ => panic!("Unexpected error reading from file: {}, err {}\n", PATH, e),
            },
        }
    }
    print!(
        "Original {} B\tCompressed {} B\n",
        total_raw, total_compressed
    );
    Ok(())
}
