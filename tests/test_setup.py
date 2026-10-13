import importlib
import sys


def test_python_environment():
    assert sys.version_info >= (3, 11), "Python 3.11+ is required"

    for package in ("pydantic", "dotenv", "pytest"):
        importlib.import_module(package)
