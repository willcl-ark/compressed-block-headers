import argparse
import logging
import sys
from enum import Enum
from io import BytesIO
from pathlib import Path
from random import randint
from time import perf_counter

import requests
from header_codec.codec import compress_headers, CompressionError, decompress_headers, \
    hash_header, HEADER_LEN

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("test_codec")
logger.setLevel(logging.DEBUG)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

REST_URL = "http://127.0.0.1:8332"
GENESIS_HEADER = b"\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00;\xa3\xed\xfdz{\x12\xb2z\xc7,>gv\x8fa\x7f\xc8\x1b\xc3\x88\x8aQ2:\x9f\xb8\xaaK\x1e^J)\xab_I\xff\xff\x00\x1d\x1d\xac+|"


class Source(Enum):
    FILE = 1
    REST =2


def header_hex(header: bytes):
    return bytes(reversed(hash_header(header))).hex()


def bitcoin_rest_request(request: str) -> bytes:
    response = requests.get(request)
    if not response.status_code == 200:
        raise requests.RequestException(
            f"could not connect to bitcoind REST API at {REST_URL}\n/"
            f"make sure bitcoind is running with -rest=1"
        )
    return response


def get_header_block(blockhash, count=2000) -> bytes:
    header_response = bitcoin_rest_request(
        f"{REST_URL}/rest/headers/{count}/{blockhash}.bin"
    )
    return header_response.content


def read_headers_file(file: Path) -> bytes:
    with open(file, "rb") as f:
        return f.read()


def get_headers(blockhash="", count=2000, height=0, to_tip=True) -> BytesIO:
    if SOURCE is Source.FILE:
        # If a height is provided, open the file this many headers in
        if height:
            start = height * HEADER_LEN
            if to_tip:
                return BytesIO(read_headers_file(args.file)[start:])
            end = start + (HEADER_LEN * count)
            return BytesIO(read_headers_file(args.file)[start:end])
        return BytesIO(read_headers_file(args.file))
    else:
        headers = BytesIO()
        if not blockhash:
            # Start from genesis hash
            best_hash = header_hex(GENESIS_HEADER)
        else:
            best_hash = blockhash

        if to_tip:
            while True:
                # Drop first header as we already have it
                header_block = get_header_block(blockhash=best_hash, count=count)[80:]
                headers.write(header_block)
                headers.seek(headers.tell() - HEADER_LEN)
                new_best_hash = header_hex(headers.read(HEADER_LEN))
                if best_hash == new_best_hash:
                    break
                best_hash = new_best_hash
        else:
            # Drop first header as we already have it
            header_block = get_header_block(blockhash=best_hash, count=count)[80:]
            headers.write(header_block)
        headers.seek(0)
        return headers


def test_codec(partial=False):
    """
    Run a test of compression and decompression.
    Asserting the input and output streams (after both operations) are identical.
    """
    logger.info(f"starting test_codec {partial=}")

    if partial:
        height = randint(0, 666600)
        if SOURCE is Source.REST:
            blockhash_response = bitcoin_rest_request(f"{REST_URL}/rest/blockhashbyheight/{height}.hex")
            blockhash = blockhash_response.text.strip()
            logger.info(f"testing 2000 headers from {height=} {blockhash=}")
            cin = get_headers(blockhash, to_tip=False)
        else:
            cin = get_headers(height=height, to_tip=False)
            blockhash = header_hex(cin.read(80))
            cin.seek(0)
    else:
        cin = get_headers()

    # Calculate number of headers in test
    cin.seek(0, 2)
    num_headers = int(cin.tell() / HEADER_LEN)
    logger.debug(f"num headers: {num_headers}")
    uncompressed_size = cin.tell()
    logger.debug(f"uncompressed header chain size: {uncompressed_size:,} B")

    # Save the hex hash of our best header
    cin.seek(0, 2)
    cin.seek(cin.tell() - HEADER_LEN)
    best_hash = header_hex(cin.read(HEADER_LEN))
    logger.debug(f"best hash: {best_hash}")

    # Get the first header
    cin.seek(0)
    first_header = cin.read(HEADER_LEN)

    # Init io streams
    cin.seek(0)
    cout = BytesIO()
    dout = BytesIO()

    # Start compression
    logger.debug(f"starting compression")
    time_start_compress = perf_counter()
    compress_headers(cin, cout)
    time_end_compress = perf_counter()
    logger.debug(f"finished compression in {round(time_end_compress - time_start_compress, 6)} seconds")
    compressed_size = cout.tell()
    logger.debug(f"compressed size: {compressed_size:,} B")

    # Load the first header into the stream so we can compare the result easier later
    cout.seek(0)
    dout.write(first_header)

    # Test decompression
    logger.debug(f"starting decompression")
    # Use the output of the compression as the input to the decompression
    t4 = perf_counter()
    decompress_headers(cout, dout, first_header)
    t5 = perf_counter()
    logger.debug(f"finished decompression in {round(t5 - t4, 6)} seconds")

    # Reset everything
    cin.seek(0)
    cout.seek(0)
    dout.seek(0)

    if not cin.read() == dout.read():
        logger.error(f"uncompressed input does not match decompressed output")
        return

    logger.info(f"compressed and decompressed {num_headers} headers in {round((time_end_compress - time_start_compress) + (t5 - t4), 2)} s")
    logger.info(f"compression saved {uncompressed_size - compressed_size:,} Bytes in total")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Test block header compression and decompression')
    parser.add_argument('-f', '--file', type=Path, help='path to a binary file containing block headers')
    args = parser.parse_args()
    if args.file:
        if args.file.exists():
            logger.info(f"using headers from {args.file}")
            SOURCE = Source.FILE
        else:
            logger.info(f"path {args.file} does not exist")
            sys.exit()
    else:
        SOURCE = Source.REST
        logger.info(f"using headers from bitcoind REST API")

    # Test 2000 headers from a random position in the chain
    test_codec(partial=True)
    # Test the entire chain
    test_codec()
