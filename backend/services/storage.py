from pathlib import Path
import shutil
from fastapi import UploadFile


def save_upload_file(upload: UploadFile, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)
