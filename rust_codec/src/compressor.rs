use crate::blockheader::BlockHeader;

pub struct Deque {
    // A 7 slot FIFO deque for storing previous version(s)
    pub(crate) queue: Vec<i32>,
}

impl Deque {
    pub fn insert(&mut self, value: i32) -> () {
        &self.queue.insert(0, value);
        &self.queue.truncate(7);
    }
}

pub(crate) struct Buffers {
    // Reusable buffers for compression and decompression
    pub(crate) b1: [u8; 1],
    pub(crate) b2: [u8; 2],
    pub(crate) b4: [u8; 4],
    pub(crate) b32: [u8; 32],
    pub(crate) b80: [u8; 80],
}

impl Buffers {
    fn new() -> Self {
        Buffers {
            b1: [0; 1],
            b2: [0; 2],
            b4: [0; 4],
            b32: [0; 32],
            b80: [0; 80],
        }
    }
}

pub(crate) struct CompressorState {
    // Stores state for a (de)compressor
    pub(crate) prev_versions: Deque,
    pub(crate) prev_header: Option<BlockHeader>,
    pub(crate) buf: Buffers,
}

impl CompressorState {
    pub(crate) fn new() -> Self {
        CompressorState {
            prev_versions: Deque { queue: Vec::new() },
            prev_header: None,
            buf: Buffers::new(),
        }
    }
}
