"""Object storage for original documents. Local-directory backend; swappable for S3 later."""

import shutil
from pathlib import Path


class ObjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def store(self, source: Path) -> str:
        """Move a file into the store; returns the storage path relative to the root."""
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.root / source.name
        if destination.exists():
            destination.unlink()
        shutil.move(str(source), str(destination))
        return source.name

    def path_for(self, storage_path: str) -> Path:
        return self.root / storage_path
