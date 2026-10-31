"""Local filesystem backup storage. Used in production when
BACKUP_BACKEND=local, and in every test (SPEC.md §7.2, §9.1) via `tmp_path`.
"""

from datetime import UTC, datetime
from pathlib import Path

from app.storage.base import BackupInfo


class LocalStorage:
    def __init__(self, directory: str) -> None:
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)

    def upload(self, name: str, data: bytes) -> str:
        path = self._directory / name
        path.write_bytes(data)
        return str(path)

    def list(self) -> list[BackupInfo]:
        # Matches both the current .xlsx format and any older .json backups
        # already on disk from before the spreadsheet-format switch, so
        # pre-existing backups don't just disappear from the list.
        paths = [*self._directory.glob("inventory-*.xlsx"), *self._directory.glob("inventory-*.json")]
        infos = []
        for path in sorted(paths):
            stat = path.stat()
            infos.append(
                BackupInfo(
                    name=path.name,
                    created_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                    size_bytes=stat.st_size,
                )
            )
        return infos

    def download(self, name: str) -> bytes:
        path = self._directory / name
        if not path.is_file():
            raise FileNotFoundError(name)
        return path.read_bytes()
