from io import BytesIO
from time import perf_counter
import requests
from random import randint
from codec import compress, decompress, HEADER_LEN, hash_header


REST_URL = "http://127.0.0.1:8332"
GENESIS_HEADER = b'\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00;\xa3\xed\xfdz{\x12\xb2z\xc7,>gv\x8fa\x7f\xc8\x1b\xc3\x88\x8aQ2:\x9f\xb8\xaaK\x1e^J)\xab_I\xff\xff\x00\x1d\x1d\xac+|'
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


def test_full():
    """
    Runs a test of the full header chain in both compression and decompression in blocks
    of 2000 headers per request.
    """
    # Init with genesis block hash
    best_hash = bytes(reversed(GENESIS_HASH)).hex()
    cout = BytesIO()
    din = BytesIO()
    dout = BytesIO()
    total = 0
    t1 = perf_counter()
    print(f"Started test at {t1}")

    while True:
        # Fetch headers from the node
        headers = get_headers(blockhash=best_hash, count=2000)
        new_best_hash = bytes(reversed(hash_header(headers[-80:]))).hex()
        if best_hash == new_best_hash:
            print(f"Reached best hash known to node: {best_hash}")
            break
        else:
            best_hash = new_best_hash
            # -1 otherwise we count the "from" header twice
            total += int((len(headers) / 80)) - 1

        # Init compressionIn with the fetched headers
        cin = BytesIO(headers)
        first_header = cin.read(HEADER_LEN)
        cin.seek(0)

        # Test compression
        compress(cin, cout)

        # Use the output of the compression as the input to the decompression
        cout.seek(0)
        din.write(cout.read())
        # Load the first header into the stream so we can compare the result easier later
        dout.write(first_header)

        # Test decompression
        decompress(din, dout, first_header)

        # Reset everything
        cin.seek(0)
        cin.truncate()
        cout.seek(0)
        cout.truncate()
        din.seek(0)
        din.truncate()
        dout.seek(0)
        dout.truncate()

    t2 = perf_counter()
    print(f"Ended test at {t2}")
    print(f"Total time: {t2-t1} s")
    print(f"Compressed and decompressed {total} headers in {round(t2-t1, 2)} s")


test_full()
