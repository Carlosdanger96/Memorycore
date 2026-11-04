"""Process-held lease for one central HTTP owner of a database target."""

from __future__ import annotations

import hashlib
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import urlsplit


def _lease_path(target: str | Path) -> Path:
    value = str(target)
    if value.startswith(("postgresql://", "postgresql+psycopg://", "postgres://")):
        url = urlsplit(value)
        value = f"postgresql://{(url.hostname or '').lower()}:{url.port or 5432}{url.path}"
    else:
        value = os.path.normcase(str(Path(value).expanduser().resolve()))
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return Path(tempfile.gettempdir()) / f"memorycore-service-{digest}.lock"


@contextmanager
def central_service_lease(target: str | Path) -> Iterator[None]:
    """Fail closed if another central service owns this target on this host.

    The OS releases the lock after a crash. The file contains no database URL
    or credentials and is never removed while the lease is held.
    """
    path = _lease_path(target)
    with path.open("a+b") as handle:
        if path.stat().st_size == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("a central Memorycore service already owns this database target") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
