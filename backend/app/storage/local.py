"""Local filesystem backup storage. Used in production when
BACKUP_BACKEND=local, and in every test (SPEC.md §7.2, §9.1) via `tmp_path`.
"""

from datetime import UTC, datetime
from pathlib import Path

from app.storage.base import BackupInfo


class LocalStorage:
    def __init__(self, directory: str) -> None:
        """Point the store at a directory.

        Args:
            directory: Where backups are written; created if missing.
        """
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)

    def _path_inside(self, name: str) -> Path:
        """A backup name reaches this layer straight from the API
        (RestoreRequest.name), and `directory / name` happily resolves an
        absolute path or one containing `..` to somewhere else entirely --
        so `{"name": "../../../etc/passwd"}` would otherwise read an
        arbitrary file. Resolving and checking containment covers
        separators, parent refs and symlinks in one go. A name that escapes
        raises FileNotFoundError, exactly like a name that simply doesn't
        exist, so the error never reveals which of the two it was."""
        base = self._directory.resolve()
        path = (base / name).resolve()
        if path != base and base not in path.parents:
            raise FileNotFoundError(name)
        return path

    def upload(self, name: str, data: bytes) -> str:
        """Write one backup into the directory.

        Args:
            name: File name, validated to stay inside the directory.
            data: File contents.

        Returns:
            str: The path written.

        Raises:
            FileNotFoundError: When the name would escape the directory.
        """
        path = self._path_inside(name)
        path.write_bytes(data)
        return str(path)

    def list(self) -> list[BackupInfo]:
        """List backups in the directory, newest first.

        Returns:
            list[BackupInfo]: Both current .xlsx and older .json backups.
        """
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
        """Read one backup from the directory.

        Args:
            name: File name, validated to stay inside the directory.

        Returns:
            bytes: The file contents.

        Raises:
            FileNotFoundError: When the file is absent, or the name would escape
                the directory -- deliberately the same error, so it never
                reveals which of the two it was.
        """
        path = self._path_inside(name)
        if not path.is_file():
            raise FileNotFoundError(name)
        return path.read_bytes()
