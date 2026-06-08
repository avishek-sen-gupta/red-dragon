"""In-memory VSAM KSDS engine backed by SortedDict."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sortedcontainers import SortedDict

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

    def __init__(self, config: FctConfig) -> None:
        self._config = config
        self._datasets: dict[str, VsamDataset] = {}
        self._cursors: dict[_CursorKey, int] = {}

    def load_all(self) -> None:
        """Load all configured datasets from their ASCII flat files."""
        for name, cfg in self._config.datasets.items():
            ds = VsamDataset(
                record_length=cfg.record_length,
                key_offset=cfg.key_offset,
                key_length=cfg.key_length,
            )
            if cfg.path.exists():
                data = cfg.path.read_bytes()
                rec_len = cfg.record_length
                for i in range(0, len(data), rec_len):
                    record = data[i : i + rec_len]
                    if len(record) == rec_len:
                        # Key is the first N bytes — caller specifies key at operation time
                        # Store with full record as key for now; keyed operations use slice
                        ds.store[record] = record
            self._datasets[name.upper()] = ds
            logger.info("VSAM: loaded %s (%d records)", name, len(ds.store))

    def dataset_count(self) -> int:
        return len(self._datasets)

    def _get_ds(self, file_name: str) -> VsamDataset | None:
        return self._datasets.get(file_name.upper().strip("'\""))

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
        return RESP_NORMAL

    def rewrite(
        self, file_name: str, key: bytes, key_length: int, record: bytes
    ) -> int:
        """REWRITE FILE. Returns eibresp."""
        ds = self._get_ds(file_name)
        if ds is None:
            return RESP_DISABLED
        klen = ds.key_length or key_length
        key_prefix = key[:klen]
        for existing in list(ds.store.keys()):
            if self._record_key(ds, existing, key_length) == key_prefix:
                del ds.store[existing]
                ds.store[bytes(record)] = bytes(record)
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
        # Find first key >= prefix (compared on the dataset's key slice)
        idx = 0
        for i, k in enumerate(keys):
            if self._record_key(ds, k, key_length) >= prefix:
                idx = i
                break
        self._cursors[cursor_key] = idx
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
        return bytes(record), RESP_NORMAL

    def readprev(
        self, file_name: str, cursor_key: _CursorKey
    ) -> tuple[bytes | None, int]:
        """READPREV FILE. Returns (record, eibresp).

        The cursor points one past the last-returned record (READNEXT
        semantics), so the previous record is two positions back from it.
        """
        ds = self._get_ds(file_name)
        if ds is None:
            return None, RESP_DISABLED
        keys = list(ds.store.keys())
        idx = self._cursors.get(cursor_key, 0) - 2
        if idx < 0:
            return None, RESP_ENDFILE
        record = keys[idx]
        self._cursors[cursor_key] = idx + 1
        return bytes(record), RESP_NORMAL

    def endbr(self, file_name: str, cursor_key: _CursorKey) -> int:
        """ENDBR FILE. Releases cursor. Returns eibresp."""
        self._cursors.pop(cursor_key, None)
        return RESP_NORMAL
