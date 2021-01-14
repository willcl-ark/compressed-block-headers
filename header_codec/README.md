# Bitcoin Header Codec

A module which allows compression and decompression of bitcoin block headers according to spec found at: 
https://github.com/willcl-ark/compressed-block-headers/blob/v1.0/compressed-block-headers.adoc

## Installation
Simply install the package to your python environment:

```bash
pip install -e .
```

## Usage
Both the compressor and decompressor take byte streams as input and byte streams as output.

Example usage:

```python
from io import BytesIO
from header_codec import *


# Get binary bitcoin block headers from somewhere (REST API... see tests.py)
headers = your_header_fetch_function()
first_header = headers[0:80]


# Compression
compression_in = BytesIO(headers)
compression_out = BytesIO()
compress_headers(compression_in, compression_out)


# Decompression
decompression_out = BytesIO()
compression_out.seek(0)  # use the output of the compression as input to decompression
decompress_headers(compression_out, decompression_out, first_header)


# Compare
compression_in.seek(80)  # skip the first header for comparison
decompression_out.seek(0)
assert compression_in.read() == decompression_out.read()
```

## Tests
To run the tests, make sure you have bitcoind running with flag `-rest=1` to enable the unauthenticated REST API which is used to fetch headers.

Next, to run the default test (entire chain compression) simply run:
```bash
python3 tests/tests.py
```

