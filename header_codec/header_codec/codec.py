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
6 sequence_end:     last header in sequence.            more headers to follow
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


import hashlib
import logging
import struct
from io import BytesIO


HEADER_LEN = 80
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger("codec")


# Bitfield masks
mask_version = 0b10000000
mask_prev_block_hash = 0b00010000
mask_time = 0b00001000
mask_nBits = 0b00000100
mask_end = 0b00000010


class CompressionError(Exception):
    pass


def hash_header(header: bytes):
    return hashlib.sha256(hashlib.sha256(header).digest()).digest()


def _compress(in_stream: BytesIO, out_stream: BytesIO):
    while True:
        in_pos_start = in_stream.tell()
        prev_header = in_stream.read(HEADER_LEN)
        next_header = in_stream.read(HEADER_LEN)
        # Rewind for the next iteration to read prev_header from the right place
        in_stream.seek(in_pos_start + HEADER_LEN)

        if not next_header:
            # Rewind the stream and set the sequence end bit of the bitfield
            # Only done once per sequence
            end = out_stream.tell()
            out_stream.seek(out_pos_start)
            bitfield = int.from_bytes(out_stream.read(1), "little") ^ mask_end
            out_stream.seek(out_pos_start)
            out_stream.write(bitfield.to_bytes(1, "little"))
            out_stream.seek(end)
            break

        # Mark where we start so we can rewind when we set the sequence_end bit
        out_pos_start = out_stream.tell()
        # Advance out_stream 1 byte for bitfield after we've configured it
        out_stream.seek(out_pos_start + 1)

        # Init empty bitfield
        bitfield = 0b00000000

        # Version
        if prev_header[0:4] == next_header[0:4]:
            bitfield = bitfield ^ mask_version
        else:
            out_stream.write(next_header[0:4])

        # Prev Block Hash always omitted
        bitfield = bitfield ^ mask_prev_block_hash

        # Merkle_root
        out_stream.write(next_header[36:68])

        # Time
        (prev_time,) = struct.unpack("I", prev_header[68:72])
        (next_time,) = struct.unpack("I", next_header[68:72])
        time_offset = next_time - prev_time
        # If we can fit it as a 2 byte offset, do that
        if -32768 < time_offset < 32767:
            bitfield = bitfield ^ mask_time
            out_stream.write(struct.pack("<h", time_offset))
        # Else copy the full 4 bytes
        else:
            out_stream.write(next_header[68:72])

        # nBits
        if prev_header[72:76] == next_header[72:76]:
            # If the same, only set the bitfield
            bitfield = bitfield ^ mask_nBits
        else:
            # Else write the new 4 byte nBits
            out_stream.write(next_header[72:76])

        # Nonce always requires full 4 bytes
        out_stream.write(next_header[76:80])
        out_pos_end = out_stream.tell()

        # Rewind to write the 1 byte bitfield
        out_stream.seek(out_pos_start)
        out_stream.write(bitfield.to_bytes(1, "little"))

        # Seek to the end ready for the next header to be appended
        out_stream.seek(out_pos_end)


def compress_headers(in_stream: BytesIO, out_stream: BytesIO) -> bool:
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
    end = False

    while not end:
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
        bitfield = int.from_bytes(in_stream.read(1), "little")

        # Version
        if bitfield & mask_version:
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
        if bitfield & mask_time:
            (time_offset,) = struct.unpack("<h", in_stream.read(2))
            prev_header.seek(68)
            (time_prev,) = struct.unpack("I", prev_header.read(4))
            prev_header.seek(0)
            out_stream.write(struct.pack("I", (time_prev + time_offset)))
        else:
            out_stream.write(in_stream.read(4))

        # nBits
        if bitfield & mask_nBits:
            prev_header.seek(72)
            out_stream.write(prev_header.read(4))
            prev_header.seek(0)
        else:
            out_stream.write(in_stream.read(4))

        # Nonce
        out_stream.write(in_stream.read(4))

        # Check if this is final header
        if bitfield & mask_end:
            end = True


def decompress_headers(
    in_stream: BytesIO, out_stream: BytesIO, prev_header: bytes
) -> bool:
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
