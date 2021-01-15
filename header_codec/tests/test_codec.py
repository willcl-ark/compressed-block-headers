import logging
from io import BytesIO
from random import randint
from time import perf_counter

import requests
from header_codec.codec import compress_headers, CompressionError, decompress_headers, \
    hash_header, HEADER_LEN

REST_URL = "http://127.0.0.1:8332"
GENESIS_HEADER = b"\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00;\xa3\xed\xfdz{\x12\xb2z\xc7,>gv\x8fa\x7f\xc8\x1b\xc3\x88\x8aQ2:\x9f\xb8\xaaK\x1e^J)\xab_I\xff\xff\x00\x1d\x1d\xac+|"
GENESIS_HASH = hash_header(GENESIS_HEADER)


logger = logging.getLogger("test_codec")
logger.setLevel(logging.DEBUG)

def bitcoin_rest_request(request: str) -> bytes:
    response = requests.get(request)
    if not response.status_code == 200:
        raise requests.RequestException(
            f"Could not connect to bitcoind REST API at {REST_URL}\n/"
            f"Make sure bitcoind is running with -rest=1"
        )
    return response


def get_headers(blockhash="", count=2000):
    if not blockhash:
        height = randint(0, 421074)
        blockhash_response = bitcoin_rest_request(
            f"{REST_URL}/rest/blockhashbyheight/{height}.hex"
        )
        blockhash = blockhash_response.text.strip()
    if not count:
        count = randint(100, 2000)

    header_response = bitcoin_rest_request(
        f"{REST_URL}/rest/headers/{count}/{blockhash}.bin"
    )
    return header_response.content


def test_random_block():
    """
    Tests compression and decompression by requesting a single block (max 2000 headers)
    from a random position in the chain.
    """
    logger.info(f"starting test_random_block")
    cin = BytesIO()
    cout = BytesIO()
    din = BytesIO()
    dout = BytesIO()
    cin.write(get_headers(count=2000))
    uncomp_size = cin.tell()
    count = int((uncomp_size / 80))
    logger.debug(f"got {count} headers from bitcoind")
    cin.seek(0)

    # Save the first uncompressed header for later
    first_header = cin.read(HEADER_LEN)
    cin.seek(0)

    # Test compression
    logger.debug("starting compression")
    t1 = perf_counter()
    if not compress_headers(cin, cout):
        raise CompressionError("during test_random_block::compress")
    t2 = perf_counter()
    logger.debug(f"finished compression in {round(t2 - t1, 6)} seconds")
    comp_size = cout.tell()

    # Rewind so we can use output of compression as input to decompression
    cout.seek(0)

    # Load the first header into output stream so we can compare the result easier later
    dout.write(first_header)

    # Test decompression
    logger.debug("starting decompression...")
    t3 = perf_counter()
    if not decompress_headers(cout, dout, first_header):
        CompressionError("during decompress")
    t4 = perf_counter()
    logger.debug(f"finished decompression in {round(t4 - t3, 6)} seconds")

    logger.info(f"compressed and decompressed {count} headers in {round(t4 - t1, 2)} seconds")
    logger.info(f"uncompressed size: {uncomp_size:,} B")
    logger.info(f"compressed size:   {comp_size:,} B")
    logger.info(f"compression saved: {uncomp_size - comp_size:,} Bytes, or {round((1 - (comp_size/uncomp_size)) * 100, 2)} %")


def test_full_sync():
    """
    Runs a test of the full header chain in both compression and decompression by
    loading the entire header chain into RAM and performing a single compression and
    decompression on the stream, asserting the input and output streams (after  both
    operations) are identical.
    """
    logger.info(f"starting test_full_sync")
    # Init with genesis block hash
    best_hash = bytes(reversed(GENESIS_HASH)).hex()
    cin = BytesIO()
    cout = BytesIO()
    dout = BytesIO()
    total = 0
    t0 = perf_counter()

    while True:
        # Fetch all headers from the node
        headers = get_headers(blockhash=best_hash, count=2000)
        new_best_hash = bytes(reversed(hash_header(headers[-80:]))).hex()
        if best_hash == new_best_hash:
            break

        best_hash = new_best_hash

        cin.write(headers)
        total = int(cin.tell() / 80)

    uncompressed_size = cin.tell()

    logger.debug(f"reached chaintip of node:")
    logger.debug(f"blockhash:         {best_hash}")
    logger.debug(f"height:            {total}")
    logger.debug(f"header chain size: {uncompressed_size:,} B")
    cin.seek(0)

    # Start compression
    cin.seek(0)
    t1 = perf_counter()
    logger.debug(f"started compression at {round(t1, 6)}")
    compress_headers(cin, cout)
    t2 = perf_counter()
    logger.debug(f"finished compression at {round(t2, 6)}")
    compressed_size = cout.tell()
    logger.debug(f"compressed size: {compressed_size:,} B")

    # Use the output of the compression as the input to the decompression
    cout.seek(0)
    # Load the first header into the stream so we can compare the result easier later
    dout.write(GENESIS_HEADER)

    # Test decompression
    t3 = perf_counter()
    logger.debug(f"started decompression at {round(t3, 6)}")
    decompress_headers(cout, dout, GENESIS_HEADER)
    t4 = perf_counter()
    logger.debug(f"finished decompression at {round(t4, 6)}")

    # Reset everything
    cin.seek(0)
    cin.truncate()
    cout.seek(0)
    cout.truncate()
    dout.seek(0)
    dout.truncate()

    if not cin.read() == dout.read():
        logger.error(f"uncompressed input does not match decompressed output")
        return

    logger.debug(f"total time including fetching headers: {round(t4 - t0, 6)} s")
    logger.info(
        f"compressed and decompressed {total} headers in {round((t2 - t1) + (t4 - t3), 2)} s"
    )
    logger.info(f"compression saved {uncompressed_size - compressed_size:,} Bytes in total")


test_random_block()
test_full_sync()
