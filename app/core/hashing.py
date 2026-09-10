import hashlib
from pathlib import Path


def hash_file(path: str | Path) -> tuple[str, str]:
    """Return (md5, sha256) hex digests for a file."""
    md5    = hashlib.md5()
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def verify_file(path: str | Path, expected_md5: str, expected_sha256: str) -> bool:
    md5, sha256 = hash_file(path)
    return md5 == expected_md5 and sha256 == expected_sha256
