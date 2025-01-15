# Simple Python Package Index Mirror
This project downloads the files needed to mirror parts of the PyPI or any other Package Index that uses the "simple" API and generates the needed index files.

## Reasoning
I am aware of two alternatives:

1. [pypi-mirror](https://github.com/montag451/pypi-mirror/)
2. [bandersnatch](https://github.com/pypa/bandersnatch/)

The first allows mirroring only specific packages while the second is a full PyPI mirror which at the time of writing would require almost 25TB of space.

Where this project (hopefully) shines is it's simplicity, instead of using `pip` to download the packages that you want to mirror it just downloads using the simple API and then builds simple API indexes.

## Limitations
- At this time dependencies that are not resolved, thus only those packages that were explicitely requested are downloaded.
While I hope to include support for dependencies it will probably involve a serious refactoring of the code.
- Only source archives (`.tar.gz`) and wheels (`.whl`) are downloaded, certain older packages have files with other extensions (`.zip`, `.exe`, etc) these are all ignored.
- Packages that use version names/numbers that don't comply with `packaging.version.Version` are ignored, a solution for this is also in the works.

## Usage
```
usage: ./simple-pypi-mirror.py [-h] [--index https://pypi.org/simple/] [--local-folder /var/www/pypi/simple/] [--ignore-errors] [--include-prereleases] [--binary-only | --source-only] (somepackage|somepackage=1.10.0|req.txt)

positional arguments:
  (somepackage|somepackage=1.10.0|req.txt)
                        Package name and optionally version or path to requirements.txt

options:
  -h, --help            show this help message and exit
  --index https://pypi.org/simple/
                        Address of PyPI simple API to use
  --local-folder /var/www/pypi/simple/
                        Folder where the simple index is stored
  --ignore-errors       Continue to the next package when there is an error
  --include-prereleases
                        Allow prerelease software to be downloaded when no version is specified.
  --binary-only         Only download binary wheel files (.whl)
  --source-only         Only download source archives (.tar.gz)
```
### Client
You can use the index built by the script by serving the directory with any webserver (apache, nginx, python http.server) if your server doesn't use TLS the `pip` command would look like this:

`pip3 install --index-url http://(HOST|IP)(|:PORT)/simple --trusted-host (HOST|IP) (package|requirement)`

If you do use TLS it *may* be possible to leave `--trusted-host` out, I have not yet tested this, the command would look like this:

`pip3 install --index-url https://(HOST|IP)(|:PORT)/simple  (package|requirement)`

## Contributing
Feel free to submit issues/PRs on this repository.

Sponsorships are also welcomed.

## License
GPLv2
Copyright 2025/5775 - E.S. Rosenberg a.k.a. Keeper of the Keys