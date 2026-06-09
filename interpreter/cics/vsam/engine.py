"""In-memory VSAM KSDS engine backed by SortedDict."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from sortedcontainers import SortedDict

from interpreter.cics.vsam.backend import InMemoryBackend, VsamBackend
from interpreter.cics.vsam.fct import FctConfig

logger = logging.getLogger(__name__)

# Browse cursor key: (task_id, file_name, cursor_id) → int index into sorted keys
_CursorKey = tuple[str, str, str]

# CICS EIBRESP codes used by file control
RESP_NORMAL = 0
RESP_NOTFND = 13
RESP_ENDFILE = 20
RESP_DUPREC = 14
RESP_DISABLED = 84
RESP_IOERR = 17


@dataclass
class VsamDataset:
    record_length: int
    # Offset/length of the key within each record (from DatasetConfig). A
    # key_offset of 0 + key_length of 0 reproduces the legacy offset-0 match.
    key_offset: int = 0
    key_length: int = 0
    store: SortedDict = field(default_factory=SortedDict)  # key_bytes → record_bytes


class VsamEngine:
    """In-memory VSAM engine. One SortedDict per dataset.

    Records are stored keyed by their full record bytes. Key matching uses the
    record slice ``record[key_offset : key_offset + klen]`` where ``key_offset``
    comes from the dataset config (default 0) and ``klen`` is the operation's
    key length (or the config's ``key_length`` when pinned). With the defaults
    this is the historical offset-0 prefix match; a non-zero ``key_offset``
    supports alternate-index paths whose key lives inside the record (e.g. the
    CARD-XREF ACCT-ID at offset 25).
    """

    def __init__(self, config: FctConfig, backend: VsamBackend | None = None) -> None:
        self._config = config
        self._backend: VsamBackend = (
            backend if backend is not None else InMemoryBackend()
        )
        self._datasets: dict[str, VsamDataset] = {}
        # Browse position cursor: a "between-records" index ``p`` in [0, len].
        # READNEXT returns keys[p] then advances; READPREV returns keys[p-1]
        # then retreats. ``_cursor_dir`` records the last browse direction so a
        # READNEXT→READPREV reversal skips back over the just-read record.
        self._cursors: dict[_CursorKey, int] = {}
        self._cursor_dir: dict[_CursorKey, str] = {}

    def load_all(self) -> None:
        """Load all configured datasets via the backend (seed or persisted state)."""
        for name, cfg in self._config.datasets.items():
            ds = VsamDataset(
                record_length=cfg.record_length,
                key_offset=cfg.key_offset,
                key_length=cfg.key_length,
            )
            for record in self._backend.load(name, cfg):
                if len(record) == cfg.record_length:
                    ds.store[record] = record
            self._datasets[name.upper()] = ds
            logger.info("VSAM: loaded %s (%d records)", name, len(ds.store))

    def dataset_count(self) -> int:
        return len(self._datasets)

    def _get_ds(self, file_name: str) -> VsamDataset | None:
        return self._datasets.get(file_name.upper().strip("'\""))

    def _persist(self, file_name: str) -> None:
        """Write-through the dataset's current records via the backend."""
        canonical = file_name.upper().strip("'\"")
        cfg = self._config.datasets.get(canonical)
        ds = self._datasets.get(canonical)
        if cfg is None or ds is None:
            return
        self._backend.persist(canonical, cfg, list(ds.store.keys()))

    @staticmethod
    def _record_key(ds: VsamDataset, record: bytes, key_length: int) -> bytes:
        """The portion of ``record`` that participates in key matching.

        Slices ``record[key_offset : key_offset + klen]`` where ``klen`` is the
        dataset's pinned ``key_length`` if set, else the operation's
        ``key_length``. With key_offset=0 and an unpinned width this is the
        legacy ``record[:key_length]`` prefix.
        """
        klen = ds.key_length or key_length
        start = ds.key_offset
        return record[start : start + klen]

    # ── Point operations ──────────────────────────────────────────────

    def read(
        self, file_name: str, key: bytes, key_length: int
    ) -> tuple[bytes | None, int]:
        """READ FILE. Returns (record_bytes, eibresp)."""
        ds = self._get_ds(file_name)
        if ds is None:
            return None, RESP_DISABLED
        klen = ds.key_length or key_length
        search = key[:klen]
        for record in ds.store.keys():
            if self._record_key(ds, record, key_length) == search:
                return bytes(record), RESP_NORMAL
        return None, RESP_NOTFND

    def write(self, file_name: str, key: bytes, key_length: int, record: bytes) -> int:
        """WRITE FILE. Returns eibresp."""
        ds = self._get_ds(file_name)
        if ds is None:
            return RESP_DISABLED
        key_prefix = self._record_key(ds, record, key_length)
        for existing in list(ds.store.keys()):
            if self._record_key(ds, existing, key_length) == key_prefix:
                return RESP_DUPREC
        ds.store[bytes(record)] = bytes(record)
        self._persist(file_name)
        return RESP_NORMAL

    def rewrite(
        self, file_name: str, key: bytes, key_length: int, record: bytes
    ) -> int:
        """REWRITE FILE. Returns eibresp."""
        ds = self._get_ds(file_name)
        if ds is None:
            return RESP_DISABLED
        # EXEC CICS REWRITE has no RIDFLD: the record key comes from the FROM
        # record's own key field. When the caller passes an empty key (the
        # REWRITE lowering, which has no RIDFLD to copy in), derive the match
        # key from the record itself — mirroring write()'s self-keyed behaviour.
        klen = ds.key_length or key_length
        key_prefix = key[:klen] if key else self._record_key(ds, record, key_length)
        for existing in list(ds.store.keys()):
            if self._record_key(ds, existing, key_length) == key_prefix:
                del ds.store[existing]
                ds.store[bytes(record)] = bytes(record)
                self._persist(file_name)
                return RESP_NORMAL
        return RESP_NOTFND

    def delete(self, file_name: str, key: bytes, key_length: int) -> int:
        """DELETE FILE. Returns eibresp."""
        ds = self._get_ds(file_name)
        if ds is None:
            return RESP_DISABLED
        klen = ds.key_length or key_length
        key_prefix = key[:klen]
        for existing in list(ds.store.keys()):
            if self._record_key(ds, existing, key_length) == key_prefix:
                del ds.store[existing]
                self._persist(file_name)
                return RESP_NORMAL
        return RESP_NOTFND

    # ── Browse operations ─────────────────────────────────────────────

    def startbr(
        self, file_name: str, key: bytes, key_length: int, cursor_key: _CursorKey
    ) -> int:
        """STARTBR FILE. Positions cursor at or after key. Returns eibresp."""
        ds = self._get_ds(file_name)
        if ds is None:
            return RESP_DISABLED
        keys = list(ds.store.keys())
        klen = ds.key_length or key_length
        prefix = key[:klen]
        # Position at the first key >= prefix (GTEQ). When no key qualifies
        # (e.g. RIDFLD = HIGH-VALUES, the CardDemo "seek last record" idiom),
        # position PAST end-of-file so the first READPREV walks back to the
        # final record. The previous code left idx=0 here, breaking that path.
        idx = len(keys)
        for i, k in enumerate(keys):
            if self._record_key(ds, k, key_length) >= prefix:
                idx = i
                break
        self._cursors[cursor_key] = idx
        self._cursor_dir.pop(cursor_key, None)
        return RESP_NORMAL

    def readnext(
        self, file_name: str, cursor_key: _CursorKey
    ) -> tuple[bytes | None, int]:
        """READNEXT FILE. Returns (record, eibresp)."""
        ds = self._get_ds(file_name)
        if ds is None:
            return None, RESP_DISABLED
        idx = self._cursors.get(cursor_key, 0)
        keys = list(ds.store.keys())
        if idx >= len(keys):
            return None, RESP_ENDFILE
        record = keys[idx]
        self._cursors[cursor_key] = idx + 1
        self._cursor_dir[cursor_key] = "next"
        return bytes(record), RESP_NORMAL

    def readprev(
        self, file_name: str, cursor_key: _CursorKey
    ) -> tuple[bytes | None, int]:
        """READPREV FILE. Returns (record, eibresp).

        The cursor ``p`` is a "between-records" position: READPREV returns
        keys[p-1] then retreats to p-1. On a READNEXT→READPREV reversal the
        cursor sits one past the just-read record, so we first skip back over
        it (matching the IBM direction-switch behaviour) before returning the
        prior record. A STARTBR→READPREV (no intervening READNEXT) walks
        straight back from the positioned point — the CardDemo "seek last
        record" idiom (STARTBR with HIGH-VALUES then READPREV).
        """
        ds = self._get_ds(file_name)
        if ds is None:
            return None, RESP_DISABLED
        keys = list(ds.store.keys())
        p = self._cursors.get(cursor_key, 0)
        if self._cursor_dir.get(cursor_key) == "next":
            # Reverse direction: step back over the record READNEXT just read.
            p -= 1
        idx = p - 1
        if idx < 0:
            return None, RESP_ENDFILE
        record = keys[idx]
        self._cursors[cursor_key] = idx
        self._cursor_dir[cursor_key] = "prev"
        return bytes(record), RESP_NORMAL

    def endbr(self, file_name: str, cursor_key: _CursorKey) -> int:
        """ENDBR FILE. Releases cursor. Returns eibresp."""
        self._cursors.pop(cursor_key, None)
        self._cursor_dir.pop(cursor_key, None)
        return RESP_NORMAL

    def flush_to(self, directory: Path) -> None:
        """Snapshot every dataset's current records to <directory>/<NAME>.dat
        via the raw codec, regardless of the configured backend."""
        from interpreter.cics.vsam.format import write_flat_file

        for name, ds in self._datasets.items():
            cfg = self._config.datasets.get(name)
            if cfg is None:
                continue
            write_flat_file(
                Path(directory) / f"{name}.dat",
                list(ds.store.keys()),
                cfg.record_length,
            )
