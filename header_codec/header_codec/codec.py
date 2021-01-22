"""
Block header compressor and decompressor
Spec: https://github.com/willcl-ark/compressed-block-headers/blob/v1.0/compressed-block-headers.adoc

Bitfield:
--------------------
Bit(s)              Set                                 Unset
-----
0                   0 - 6 indicates same as previous
1 version:          n'th version.
2                   7 indicates new distinct version
-----
3 prev_block_hash:  32 bytes included.                  Omitted (0 bytes)
4 timestamp:        2 byte offset from previous.        new 4 byte timestamp to follow
5 nBits:            same as previous (0 byte field).    new 4 byte field to follow
6
7

Uncompressed header structure:
---------------------
version         0:4
prev_block_hash 4:36
merkle_root     36:68
time            68:72
nBits           72:76
nonce           76:80
"""

import ctypes
import hashlib
import logging
import struct
from collections import deque
from dataclasses import dataclass
from io import BytesIO
from types import SimpleNamespace

HEADER_LEN = 80
logger = logging.getLogger("header_codec")

# fmt: off
# Bitfield masks
MASK_VERSION         = 0b111 << 5
MASK_PREV_BLOCK_HASH = 0b1   << 4
MASK_TIME            = 0b1   << 3
MASK_NBITS           = 0b1   << 2
MASK_END             = 0b1   << 1
NEW_DISTINCT_VERSION = 7
# fmt: on

# Min and Max int values for our 2 byte time offset
MAX_INT = int((ctypes.c_uint16(-1).value - 1) / 2)
MIN_INT = -int((ctypes.c_uint16(-1).value + 1) / 2)


class CompressionError(Exception):
    pass


@dataclass
class Header:
    __slots__ = ["version", "prev_block_hash", "merkle_root", "time", "nBits", "nonce"]
    version: bytes
    prev_block_hash: bytes
    merkle_root: bytes
    time: bytes
    nBits: bytes
    nonce: bytes

    @classmethod
    def from_bytes(cls, header):
        if not len(header) == 80:
            raise ValueError(f"Header length {len(header)} cannot be decoded")
        return cls(
            header[0:4],
            header[4:36],
            header[36:68],
            header[68:72],
            header[72:76],
            header[76:80],
        )

    @property
    def hash(self):
        return hashlib.sha256(hashlib.sha256(self.to_bytes).digest()).digest()

    @property
    def to_bytes(self):
        return b"".join(
            [
                self.version,
                self.prev_block_hash,
                self.merkle_root,
                self.time,
                self.nBits,
                self.nonce,
            ]
        )


@dataclass
class CompressorState:
    prev_versions: deque = deque(maxlen=7)
    prev_header = False  # Will mutate to Header after first cycle


@dataclass
class Codec:
    """
    A stateful codec which, for the life of the object, will store previous header state
    in order to enable header compression for a single peer.
    """

    compressor = CompressorState()
    decompressor = CompressorState()

    def _compress(self, header: bytes) -> bytes:
        # Initialise fields
        bitfield = 0b00000000
        version = b""
        prev_block_hash = b""
        merkle_root = b""
        time = b""
        nBits = b""
        nonce = b""
        header = Header.from_bytes(header)

        # Version
        if header.version in self.compressor.prev_versions:
            bitfield = bitfield ^ (
                self.compressor.prev_versions.index(header.version) << 5
            )
        else:
            self.compressor.prev_versions.appendleft(header.version)
            bitfield = bitfield ^ (NEW_DISTINCT_VERSION << 5)
            version = header.version

        # Prev Block Hash
        # We send the first of each session
        if not self.compressor.prev_header:
            prev_block_hash = header.prev_block_hash
            bitfield = bitfield ^ MASK_PREV_BLOCK_HASH
        # Otherwise always omit
        else:
            ...

        # Merkle_root always included
        merkle_root = header.merkle_root

        # Time
        if not self.compressor.prev_header:
            time = header.time
        else:
            (prev_time,) = struct.unpack("I", self.compressor.prev_header.time)
            (header_time,) = struct.unpack("I", header.time)
            time_offset = header_time - prev_time
            # If we can fit it as a 2 byte offset, do that
            if MIN_INT <= time_offset <= MAX_INT:
                bitfield = bitfield ^ MASK_TIME
                time = struct.pack("<h", time_offset)
            # Else copy the full 4 bytes
            else:
                time = header.time

        # nBits
        if not self.compressor.prev_header:
            nBits = header.nBits
        elif header.nBits == self.compressor.prev_header.nBits:
            # If the same, only set the bitfield
            bitfield = bitfield ^ MASK_NBITS
        else:
            # Else write the new 4 byte nBits
            nBits = header.nBits

        # Nonce always requires full 4 bytes
        nonce = header.nonce

        # Write the final bitfield to 1 byte
        bitfield = bitfield.to_bytes(1, "little")

        # Set compressor's prev_header to header
        self.compressor.prev_header = header

        # Return compressed header with prepended bitfield
        return b"".join(
            [
                bitfield,
                version,
                prev_block_hash,
                merkle_root,
                time,
                nBits,
                nonce,
            ]
        )

    def compress_header(self, header: bytes) -> bytes:
        """
        Compress takes a header and returns a compressed version

        :return bytes compressed header
        """
        try:
            compressed_header = self._compress(header)
        # Likely an error from stream reading or writing
        except OSError as e:
            logger.exception(e)
        # An error with packing or unpacking with struct
        except struct.error as e:
            logger.exception(e)
        return compressed_header

    def _decompress(self, header: bytes) -> bytes:
        header = BytesIO(header)
        bitfield = int.from_bytes(header.read(1), "little")
        version = b""
        prev_block_hash = b""
        merkle_root = b""
        time = b""
        nBits = b""
        nonce = b""

        # Version
        v_index = bitfield >> 5
        if v_index == NEW_DISTINCT_VERSION:
            # Version not in previous 7 distinct versions
            version = header.read(4)
            self.decompressor.prev_versions.appendleft(version)
        else:
            version = self.decompressor.prev_versions[v_index]

        # Prev_block_hash
        if bitfield & MASK_PREV_BLOCK_HASH:
            prev_block_hash = header.read(32)
        else:
            prev_block_hash = self.decompressor.prev_header.hash

        # Merkle_root
        merkle_root = header.read(32)

        # Time
        if bitfield & MASK_TIME:
            (time_offset,) = struct.unpack("<h", header.read(2))
            (time_prev,) = struct.unpack("I", self.decompressor.prev_header.time)
            time = struct.pack("I", (time_prev + time_offset))
        else:
            time = header.read(4)

        # nBits
        if bitfield & MASK_NBITS:
            nBits = self.decompressor.prev_header.nBits
        else:
            nBits = header.read(4)

        # Nonce
        nonce = header.read(4)

        header = Header(version, prev_block_hash, merkle_root, time, nBits, nonce)
        self.decompressor.prev_header = header
        return header.to_bytes

    def decompress_header(self, header: bytes) -> Header:
        """
        decompress takes a stream of compressed header(s) of length (start ... end) and a
        previous_header bytes object.
        It decompresses all compressed headers and inserts them into the return stream,
        excluding the previous_header.

        :return bool indicating success
        """
        try:
            header = self._decompress(header)
        # Likely an error from stream reading or writing
        except OSError as e:
            logger.exception(e)
        # An error with packing or unpacking with struct
        except struct.error as e:
            logger.exception(e)
        return header
