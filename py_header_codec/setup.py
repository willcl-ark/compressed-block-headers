import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="py_header_codec",
    version="0.0.1",
    author="Will Clark",
    author_email="will8clark@gmail.com  ",
    description="A bitcoin block header compressor and decompressor",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/willcl-ark/compressed-block-headers",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8',
)
