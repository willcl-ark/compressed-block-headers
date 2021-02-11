use crate::blockheader::BlockHeader;
use crate::compressor::CompressorState;
use std::convert::TryInto;
use std::io::{Error, Read, Write};

const NEW_VERSION: u8 = 7;
const MASK_VERSION: u8 = 7 << 5;
const MASK_PREV_BLOCK_HASH: u8 = 1 << 4;
const MASK_TIME: u8 = 1 << 3;
const MASK_NBITS: u8 = 1 << 2;
// const MASK_END: u8 = 1 << 1;     // Not implemented yet

// Codec with stateful compression and decompression.
// One Codec object required per connection to store previously transmitted
// header.
pub struct Codec {
    compressor: CompressorState,
    decompressor: CompressorState,
}

impl Codec {
    pub fn new() -> Self {
        Codec {
            compressor: CompressorState::new(),
            decompressor: CompressorState::new(),
        }
    }

    // Read an 80 byte uncompressed header from `input`, compress it and write
    // the result to `output`.
    // Returns the number of bytes written to `output`.
    pub fn compress<R: Read, W: Write>(
        &mut self,
        input: &mut R,
        output: &mut W,
    ) -> Result<usize, Error> {
        input.read_exact(&mut self.compressor.buf.b80)?;
        let header = BlockHeader::deserialize(&self.compressor.buf.b80.to_vec());

        let mut bitfield: u8 = 0b00000000;
        let mut result: Vec<u8> = Vec::new();

        // Version
        if self
            .compressor
            .prev_versions
            .queue
            .contains(&header.version)
        {
            // Version *is* in previous 7 distinct versions transmitted
            // TODO: Surely there's a nicer way of doing this? .index()?
            let index = self
                .compressor
                .prev_versions
                .queue
                .iter()
                .position(|&x| x == header.version)
                .unwrap();
            bitfield = bitfield ^ ((index as u8) << 5);
        } else {
            // A new distinct version
            self.compressor.prev_versions.insert(header.version);
            bitfield = bitfield ^ MASK_VERSION;
            for byte in &header.version.to_le_bytes() {
                result.push(*byte);
            }
        }

        // Prev Block Hash
        // Only send prev_block_hash with first header of the connection session
        match &self.compressor.prev_header {
            Some(_) => {
                // Set the bitflag to indicate prev_block_hash omitted
                bitfield = bitfield ^ MASK_PREV_BLOCK_HASH;
            }
            None => {
                for byte in &header.prev_block_hash {
                    result.push(*byte);
                }
            }
        }

        // Merkle Root
        for byte in &header.merkle_root {
            result.push(*byte);
        }

        // Time
        match &self.compressor.prev_header {
            // We've already sent a header, only send a 2 byte i16 offset
            Some(prev_header) => {
                let time_offset: i64 = header.time as i64 - prev_header.time as i64;
                // Sanity check to make sure the offset won't wrap when fitting into an i16
                if (time_offset <= i16::MAX as i64) && (time_offset >= i16::MIN as i64) {
                    let time_offset = header.time.wrapping_sub(prev_header.time) as i16;
                    for byte in time_offset.to_le_bytes().as_ref() {
                        result.push(*byte);
                    }
                    bitfield = bitfield ^ MASK_TIME;
                } else {
                    for byte in &header.time.to_le_bytes() {
                        result.push(*byte);
                    }
                }
            }
            // We've not send a header in this session, send a full 4 byte u32
            None => {
                for byte in &header.time.to_le_bytes() {
                    result.push(*byte);
                }
            }
        }

        // n_bits
        match &self.compressor.prev_header {
            // We've sent a header previously
            Some(prev_header) => {
                // If n_bits are the same as previous, only set the bitfield
                if header.n_bits == prev_header.n_bits {
                    bitfield = bitfield ^ MASK_NBITS;
                // else leave the bitfield unset and send the new n_bits
                } else {
                    for byte in &header.n_bits.to_le_bytes() {
                        result.push(*byte);
                    }
                }
            }
            // We've not sent a header before, send full n_bits
            None => {
                for byte in &header.n_bits.to_le_bytes() {
                    result.push(*byte);
                }
            }
        }

        // Nonce always required
        for byte in &header.nonce.to_le_bytes() {
            result.push(*byte);
        }

        // Write the bitfield to the first byte of the result vector
        result.insert(0, bitfield);

        // Update compressor's prev_header to current header
        self.compressor.prev_header = Some(header);

        // Write the compressed header and return size of compressed header
        output.write_all(&result[..])?;
        Ok(result[..].len())
    }

    // Progressively reads a compressed, variable-length blockheader from `input`, decompresses it
    // and writes the uncompressed 80B header to `output`
    // Returns num bytes written.
    pub fn decompress<R: Read, W: Write>(
        &mut self,
        input: &mut R,
        output: &mut W,
    ) -> Result<usize, Error> {
        let mut header = BlockHeader::new();

        // Read the bitfield
        input.read_exact(&mut self.decompressor.buf.b1)?;
        let bitfield: u8 = u8::from_le_bytes(self.decompressor.buf.b1.try_into().unwrap());

        // Version
        let version_index = bitfield >> 5;
        match version_index {
            NEW_VERSION => {
                // Read a full 4 bytes
                input.read_exact(&mut self.decompressor.buf.b4)?;
                // Convert to u32
                header.version = i32::from_le_bytes(self.decompressor.buf.b4.try_into().unwrap());
                // Add it to the prev_versions deque
                self.decompressor
                    .prev_versions
                    .insert(header.version.clone());
            }
            _ => {
                // Lookup the version from the deque using v_index
                header.version = self.decompressor.prev_versions.queue[version_index as usize];
            }
        }

        // Prev_block_hash
        match bitfield & MASK_PREV_BLOCK_HASH {
            MASK_PREV_BLOCK_HASH => {
                // Calculate it from the cached previous header received
                header.prev_block_hash = self.decompressor.prev_header.as_ref().unwrap().hash();
            }
            _ => {
                // Read the full 32B from input
                input.read_exact(&mut self.decompressor.buf.b32)?;
                header.prev_block_hash = self.decompressor.buf.b32.clone();
            }
        }

        // Merkle root
        input.read_exact(&mut self.decompressor.buf.b32)?;
        header.merkle_root = self.decompressor.buf.b32.try_into().unwrap();

        // Time
        match bitfield & MASK_TIME {
            // 2 Byte offset
            MASK_TIME => {
                input.read_exact(&mut self.decompressor.buf.b2)?;
                let time_offset: i64 =
                    i16::from_le_bytes(self.decompressor.buf.b2.try_into().unwrap()) as i64;
                let prev_time: i64 =
                    i64::from(self.decompressor.prev_header.as_ref().unwrap().time.clone());
                header.time = (prev_time + time_offset) as u32;
            }
            // Full 4 bytes
            _ => {
                input.read_exact(&mut self.decompressor.buf.b4)?;
                header.time = u32::from_le_bytes(self.decompressor.buf.b4.try_into().unwrap());
            }
        }

        // n_bits
        match bitfield & MASK_NBITS {
            // Same as previous
            MASK_NBITS => {
                header.n_bits = self.decompressor.prev_header.as_ref().unwrap().n_bits;
            }
            // Full 4 bytes
            _ => {
                input.read_exact(&mut self.decompressor.buf.b4)?;
                header.n_bits = u32::from_le_bytes(self.decompressor.buf.b4.try_into().unwrap());
            }
        }

        // Nonce
        input.read_exact(&mut self.decompressor.buf.b4)?;
        header.nonce = u32::from_le_bytes(self.decompressor.buf.b4.try_into().unwrap());

        // Write serialize the header into `output`
        output.write_all(&header.serialize()[..])?;

        // Clone it into `prev_header`
        self.decompressor.prev_header = Some(header.clone());

        Ok(header.serialize()[..].len())
    }
}
