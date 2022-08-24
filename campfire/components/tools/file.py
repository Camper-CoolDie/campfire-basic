from typing import Union
import os.path

dirpath = os.path.join(__file__, "../..")

def path(filepath: str) -> str:
    return os.path.normpath(os.path.join(dirpath, filepath))

def read(filepath: str) -> Union[bytes, None]:
    if os.path.exists(filepath):
        with open(filepath, "rb") as f:
            return f.read()
    else:
        return None

def write(filepath: str, content: bytes) -> None:
    with open(filepath, "wb") as f:
        f.write(content)