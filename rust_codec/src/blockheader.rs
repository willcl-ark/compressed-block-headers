use sha2::{Digest, Sha256};
use std::convert::TryInto;

// A Blockheader which can hold both compressed and uncompressed headers
#[derive(Clone, Debug)]
pub struct BlockHeader {
    pub(crate) version: i32,
    pub(crate) prev_block_hash: [u8; 32],
    pub(crate) merkle_root: [u8; 32],
    pub(crate) time: u32,
    pub(crate) n_bits: u32,
    pub(crate) nonce: u32,
}

impl BlockHeader {
    pub fn new() -> BlockHeader {
        BlockHeader {
            version: 0,
            prev_block_hash: [0; 32],
            merkle_root: [0; 32],
            time: 0,
            n_bits: 0,
            nonce: 0,
        }
    }

    // Takes an 80 byte vector
    pub fn deserialize(header: &Vec<u8>) -> BlockHeader {
        BlockHeader {
            version: i32::from_le_bytes(header[0..4].try_into().unwrap()),
            prev_block_hash: header[4..36].try_into().unwrap(),
            merkle_root: header[36..68].try_into().unwrap(),
            time: u32::from_le_bytes(header[68..72].try_into().unwrap()),
            n_bits: u32::from_le_bytes(header[72..76].try_into().unwrap()),
            nonce: u32::from_le_bytes(header[76..80].try_into().unwrap()),
        }
    }

    pub fn serialize(&self) -> Vec<u8> {
        let mut buffer: Vec<u8> = Vec::new();
        buffer.append(&mut self.version.to_le_bytes().to_vec());
        buffer.append(&mut self.prev_block_hash.to_vec());
        buffer.append(&mut self.merkle_root.to_vec());
        buffer.append(&mut self.time.to_le_bytes().to_vec());
    	buffer.append(&mut self.n_bits.to_le_bytes().to_vec());
        buffer.append(&mut self.nonce.to_le_bytes().to_vec());
        buffer
    }

    pub fn hash(&self) -> [u8; 32] {
        let mut hasher = Sha256::new();
        hasher.update(&self.version.to_le_bytes());
        hasher.update(&self.prev_block_hash);
        hasher.update(&self.merkle_root);
        hasher.update(&self.time.to_le_bytes());
        hasher.update(&self.n_bits.to_le_bytes());
        hasher.update(&self.nonce.to_le_bytes());

        let result = hasher.finalize();
        result.into()
    }
}
