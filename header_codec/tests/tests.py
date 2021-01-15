from io import BytesIO
from time import perf_counter
import requests
from random import randint
from header_codec.codec import compress_headers, decompress_headers, HEADER_LEN, hash_header, CompressionError


REST_URL = "http://127.0.0.1:8332"
GENESIS_HEADER = b"\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00;\xa3\xed\xfdz{\x12\xb2z\xc7,>gv\x8fa\x7f\xc8\x1b\xc3\x88\x8aQ2:\x9f\xb8\xaaK\x1e^J)\xab_I\xff\xff\x00\x1d\x1d\xac+|"
GENESIS_HASH = hash_header(GENESIS_HEADER)


def test_connection():
    _test = requests.get(f"{REST_URL}/rest/blockhashbyheight/{0}.hex")
    if not _test.status_code == 200:
        raise requests.RequestException(
            f"Could not connect to bitcoind REST API at {REST_URL}\n/"
            f"Make sure bitcoind is running with -rest=1"
        )


def get_headers(blockhash="", count=2000):
    test_connection()
    if not blockhash:
        height = randint(0, 421074)
        blockhash_response = requests.get(
            f"{REST_URL}/rest/blockhashbyheight/{height}.hex"
        )
        blockhash = blockhash_response.text.strip()
    if not count:
        count = randint(100, 2000)

    header_response = requests.get(f"{REST_URL}/rest/headers/{count}/{blockhash}.bin")
    return header_response.content


def test_random_block():
    """
    Tests compression and decompression by requesting a single block (max 2000 headers)
    from a random position in the chain.
    """
    cin = BytesIO()
    cout = BytesIO()
    din = BytesIO()
    dout = BytesIO()
    print(f"starting test...")
    cin.write(get_headers(count=2000))
    uncomp_size = cin.tell()
    count = int((uncomp_size / 80))
    cin.seek(0)

    # Save the first uncompressed header for later
    first_header = cin.read(HEADER_LEN)
    cin.seek(0)

    # Test compression
    print("starting compression...")
    t1 = perf_counter()
    if not compress_headers(cin, cout):
        raise CompressionError("during compress")
    t2 = perf_counter()
    print(f"finished compression in {t2-t1} seconds")
    comp_size = cout.tell()

    # Rewind so we can use output of compression as input to decompression
    cout.seek(0)

    # Load the first header into output stream so we can compare the result easier later
    dout.write(first_header)

    # Test decompression
    print("starting decompression...")
    t3 = perf_counter()
    if not decompress_headers(cout, dout, first_header):
        CompressionError("during decompress")
    t4 = perf_counter()
    print(f"finished decompression in {t4-t3} seconds")

    print(f"compressed and decompressed {count} headers in {round(t4-t1, 2)} seconds")
    print(f"uncompressed size: {uncomp_size} B")
    print(f"compressed size:   {comp_size} B")
    print(f"compression saved: {uncomp_size - comp_size} B")


def test_full_sync():
    """
    Runs a test of the full header chain in both compression and decompression by
    loading the entire header chain into RAM and performing a single compression and
    decompression on the stream, asserting the input and output streams (after  both
    operations) are identical.
    """
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

    print(f"reached best hash known to node")
    print(f"blockhash: {best_hash}")
    print(f"height:    {total}")
    print(f"uncompressed size: {uncompressed_size:,} B")
    cin.seek(0)

    # Start compression
    cin.seek(0)
    t1 = perf_counter()
    print(f"started compression at {t1}")
    compress_headers(cin, cout)
    t2 = perf_counter()
    print(f"finished compression at {t2}")
    compressed_size = cout.tell()
    print(f"compressed size: {compressed_size:,} B")

    # Use the output of the compression as the input to the decompression
    cout.seek(0)
    # Load the first header into the stream so we can compare the result easier later
    dout.write(GENESIS_HEADER)

    # Test decompression
    t3 = perf_counter()
    print(f"started decompression at {t3}")
    decompress_headers(cout, dout, GENESIS_HEADER)
    t4 = perf_counter()
    print(f"finished decompression at {t4}")

    # Reset everything
    cin.seek(0)
    cin.truncate()
    cout.seek(0)
    cout.truncate()
    dout.seek(0)
    dout.truncate()

    assert cin.read() == dout.read()

    print(f"total time including fetching headers: {t4-t0} s")
    print(
        f"compressed and decompressed {total} headers in {round((t2-t1) + (t4-t3), 2)} s"
    )
    print(f"compression saved {uncompressed_size - compressed_size:,} Bytes in total")


test_random_block()
# test_full_sync()
