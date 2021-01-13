"""
Block header compressor and decompressor
Spec: https://github.com/willcl-ark/compressed-block-headers/blob/v1.0/compressed-block-headers.adoc

Bitfield:
--------------------
Bit                 Set                                 Unset
0 version:          same as previous (0 byte field).    new 4 byte version to follow
1
2
3 prev_block_hash:  omitted (0 byte field).             new 4 byte hash to follow
4 timestamp:        2 byte offset from previous.        new 4 byte timestamp to follow
5 nBits:            same as previous (0 byte field).    new 4 byte field to follow
6
7

Header structure:
---------------------
version         0:4
prev_block_hash 4:36
merkle_root     36:68
time            68:72
nBits           72:76
nonce           76:80
"""


import hashlib
import logging
import struct
from io import BytesIO

from bitarray import bitarray

HEADER_LEN = 80
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger("codec")


class CompressionError(Exception):
    pass


def hash_header(header: bytes):
    return hashlib.sha256(hashlib.sha256(header).digest()).digest()


def _compress(in_stream: BytesIO, out_stream: BytesIO):
    while True:
        in_pos_start = in_stream.tell()
        out_pos_start = out_stream.tell()
        prev_header = in_stream.read(HEADER_LEN)
        next_header = in_stream.read(HEADER_LEN)
        # Rewind for the next iteration to read prev_header from the right place
        in_stream.seek(in_pos_start + HEADER_LEN)

        # Break here if we reached stream EOF
        if next_header == b"":
            break

        # Init empty bitfield
        bitfield = bitarray("00000000", endian="little")
        # Advance out_stream a byte to leave room for our bitfield after we've set it
        out_stream.seek(out_pos_start + 1)

        # Version
        if prev_header[0:4] == next_header[0:4]:
            bitfield[0] = 1
        else:
            out_stream.write(next_header[0:4])

        # Prev Block Hash omitted
        ...

        # Merkle_root
        out_stream.write(next_header[36:68])

        # Time
        (prev_time,) = struct.unpack("I", prev_header[68:72])
        (next_time,) = struct.unpack("I", next_header[68:72])
        time_offset = next_time - prev_time
        # If we can fit it as a 2 byte offset, do that
        if -32768 < time_offset < 32767:
            bitfield[4] = 1
            out_stream.write(struct.pack("<h", time_offset))
        # Else copy the full 4 bytes
        else:
            out_stream.write(next_header[68:72])

        # nBits
        if prev_header[72:76] == next_header[72:76]:
            # If the same, only set the bitfield
            bitfield[5] = 1
        else:
            # Else write the new 4 byte nBits
            out_stream.write(next_header[72:76])

        # Nonce always requires full 4 bytes
        out_stream.write(next_header[76:80])
        out_pos_end = out_stream.tell()

        # Rewind to write the 1 byte bitfield
        out_stream.seek(out_pos_start)
        out_stream.write(bitfield.tobytes())

        # Seek to the end ready for the next header to be appended
        out_stream.seek(out_pos_end)


def compress(in_stream: BytesIO, out_stream: BytesIO) -> bool:
    """
    Compress takes a stream of headers of length (start ... end)
    It compresses and returns (start + 1 ... end) into a return stream

    :return bool indicating success
    """
    try:
        _compress(in_stream, out_stream)
    # Likely an error from stream reading or writing
    except OSError as e:
        logger.exception(e)
        return False
    # An error with packing or unpacking with struct
    except struct.error as e:
        logger.exception(e)
        return False

    return True


def _decompress(in_stream: BytesIO, out_stream: BytesIO, prev_header: bytes):
    first = True
    while True:
        # On the first iteration only prev_header is taken from function parameter
        if first:
            prev_header = BytesIO(prev_header)
            first = False
        # Else we rewind the out stream and extract it from there
        else:
            out_pos_start = out_stream.tell()
            out_stream.seek(out_pos_start - 80)
            prev_header = BytesIO(out_stream.read(HEADER_LEN))

        # Bitfield
        bitfield = bitarray(endian="little")
        b = in_stream.read(1)
        if b == b"":
            # EOF reached
            break
        bitfield.frombytes(b)

        # Version
        if bitfield[0]:
            out_stream.write(prev_header.read(4))
            prev_header.seek(0)
        else:
            out_stream.write(in_stream.read(4))

        # Prev_block_hash
        out_stream.write(hash_header(prev_header.read(HEADER_LEN)))
        prev_header.seek(0)

        # Merkle_root
        out_stream.write(in_stream.read(32))

        # Time
        if bitfield[4]:
            (time_offset,) = struct.unpack("<h", in_stream.read(2))
            prev_header.seek(68)
            (time_prev,) = struct.unpack("I", prev_header.read(4))
            prev_header.seek(0)
            out_stream.write(struct.pack("I", (time_prev + time_offset)))
        else:
            out_stream.write(in_stream.read(4))

        # nBits
        if bitfield[5]:
            prev_header.seek(72)
            out_stream.write(prev_header.read(4))
            prev_header.seek(0)
        else:
            out_stream.write(in_stream.read(4))

        # Nonce
        out_stream.write(in_stream.read(4))


def decompress(in_stream: BytesIO, out_stream: BytesIO, prev_header: bytes) -> bool:
    """
    decompress takes a stream of compressed header(s) of length (start ... end) and a
    previous_header bytes object.
    It decompresses all compressed headers and inserts them into the return stream,
    excluding the previous_header.

    :return bool indicating success
    """
    try:
        _decompress(in_stream, out_stream, prev_header)
    # Likely an error from stream reading or writing
    except OSError as e:
        logger.exception(e)
        return False
    # An error with packing or unpacking with struct
    except struct.error as e:
        logger.exception(e)
        return False

    return True
