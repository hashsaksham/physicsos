import os
import uuid

UPLOAD_DIR = "uploads"


async def save_upload_file(file_bytes: bytes, filename: str) -> str:
    ext = os.path.splitext(filename)[1]
    unique_name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, unique_name)
    with open(path, "wb") as f:
        f.write(file_bytes)
    return path


def get_file_path(filename: str) -> str:
    return os.path.join(UPLOAD_DIR, filename)
