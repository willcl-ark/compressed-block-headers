"""
Block header compressor and decompressor
Spec: https://github.com/willcl-ark/compressed-block-headers/blob/v1.0/compressed-block-headers.adoc

Bitfield:

Bit                 Set                                 Unset
0 version:          same as previous (0 byte field).    new 4 byte version to follow
1
2
3 prev_block_hash:  omitted (0 byte field).             new 4 byte hash to follow
4 timestamp:        2 byte offset from previous.        new 4 byte timestamp to follow
5 nBits:            same as previous (0 byte field).    new 4 byte field to follow
6 msg end:          last header in sequence.            more headers to follow
7
"""
import hashlib
from io import BytesIO
import logging

import attr
from bitarray import bitarray

HEADER_LEN = 80

logger = logging.getLogger(__name__)


class CompressionError(Exception):
    pass


def hash_header(header: bytes):
    return hashlib.sha256(hashlib.sha256(header).digest()).digest()


@attr.s(slots=True, eq=False)
class Header(object):
    version = attr.ib()
    prev_block_hash = attr.ib()
    merkle_root = attr.ib()
    time = attr.ib()
    nBits = attr.ib()
    nonce = attr.ib()
    bitfield = attr.ib(default=bitarray("00000000", endian="little"))
    time_offset = attr.ib(default=0)

    def __eq__(self, other):
        return (
            self.version == other.version
            and self.prev_block_hash == other.prev_block_hash
            and self.merkle_root == other.merkle_root
            and self.time == other.time
            and self.nBits == other.nBits
            and self.nonce == other.nonce
        )

    @classmethod
    def uncompressed_from_stream(cls, stream: BytesIO):
        version = stream.read(4)
        if not version:
            raise EOFError
        prev_block_hash = stream.read(32)
        merkle_root = stream.read(32)
        time = stream.read(4)
        nBits = stream.read(4)
        nonce = stream.read(4)
        return cls(
            version=version,
            prev_block_hash=prev_block_hash,
            merkle_root=merkle_root,
            time=time,
            nBits=nBits,
            nonce=nonce,
        )
