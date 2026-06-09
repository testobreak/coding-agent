import hashlib


def file_hash(path: str) -> str:

    sha = hashlib.sha256()

    with open(path, "rb") as f:

        while chunk := f.read(8192):
            sha.update(chunk)

    return sha.hexdigest()