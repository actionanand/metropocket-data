from __future__ import annotations

import csv
import gzip
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
SUPPORTED_SCHEMA_VERSION = 1
STATUS_VALUES = {"operational", "under-construction", "planned", "temporarily-closed"}


class DataError(ValueError):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DataError(f"Missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DataError(f"Invalid JSON in {path}: {exc}") from exc


def require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DataError(f"{field} must be a non-empty string")
    return value.strip()


def require_positive_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise DataError(f"{field} must be a positive integer")
    return value


def optional_string(value: Any, field: str) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise DataError(f"{field} must be a string when supplied")
    return value.strip()


def load_pack_meta(folder: Path, expected_type: str) -> dict[str, Any]:
    meta = load_json(folder / "pack.json")
    if not isinstance(meta, dict):
        raise DataError(f"{folder / 'pack.json'} must contain an object")
    require_string(meta.get("id"), "id")
    if meta.get("type") != expected_type:
        raise DataError(f"{folder}: type must be {expected_type!r}")
    require_string(meta.get("name"), "name")
    require_positive_int(meta.get("version"), "version")
    if meta.get("schemaVersion") != SUPPORTED_SCHEMA_VERSION:
        raise DataError(f"{folder}: schemaVersion must be {SUPPORTED_SCHEMA_VERSION}")
    if "description" in meta:
        optional_string(meta["description"], "description")
    changes = meta.get("changes", [])
    if not isinstance(changes, list) or any(not isinstance(item, str) for item in changes):
        raise DataError("changes must be an array of strings")
    return meta


def read_csv(path: Path, required_columns: Iterable[str]) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            missing = [column for column in required_columns if column not in fieldnames]
            if missing:
                raise DataError(f"{path}: missing CSV columns: {', '.join(missing)}")
            rows = []
            for line_number, row in enumerate(reader, start=2):
                clean = {key: (value or "").strip() for key, value in row.items() if key is not None}
                if not any(clean.values()):
                    continue
                clean["__line__"] = str(line_number)
                rows.append(clean)
            return rows
    except FileNotFoundError as exc:
        raise DataError(f"Missing required file: {path}") from exc


def unique_ids(rows: list[dict[str, str]], field: str, label: str) -> set[str]:
    values: set[str] = set()
    for row in rows:
        value = require_string(row.get(field), f"{label}.{field} (line {row.get('__line__')})")
        if value in values:
            raise DataError(f"Duplicate {label} {field} {value!r}")
        values.add(value)
    return values


def parse_float(value: str, field: str, allow_blank: bool = True, minimum: float | None = None) -> float | None:
    if value == "" and allow_blank:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise DataError(f"{field} must be numeric") from exc
    if minimum is not None and parsed < minimum:
        raise DataError(f"{field} must be >= {minimum}")
    return parsed


def parse_int(value: str, field: str, allow_blank: bool = False, minimum: int | None = None) -> int | None:
    if value == "" and allow_blank:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DataError(f"{field} must be an integer") from exc
    if minimum is not None and parsed < minimum:
        raise DataError(f"{field} must be >= {minimum}")
    return parsed


def parse_bool01(value: str, field: str) -> int:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return 1
    if normalized in {"0", "false", "no", "n"}:
        return 0
    raise DataError(f"{field} must be 0/1 or true/false")


def open_database(path: Path, schema_path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(schema_path.read_text(encoding="utf-8"))
    return connection


def put_metadata(connection: sqlite3.Connection, values: dict[str, Any]) -> None:
    rows = []
    for key, value in values.items():
        if value is None:
            continue
        rows.append((key, json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)))
    connection.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", rows)


def deterministic_gzip(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, target.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as gz:
            shutil.copyfileobj(src, gz)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def release_url(repository: str, tag: str, filename: str) -> str:
    repository = require_string(repository, "repository")
    tag = require_string(tag, "tag")
    return f"https://github.com/{repository}/releases/download/{tag}/{filename}"


def pack_descriptor(
    meta: dict[str, Any],
    db_path: Path,
    gz_path: Path,
    repository: str,
    tag: str,
) -> dict[str, Any]:
    descriptor: dict[str, Any] = {
        "id": meta["id"],
        "type": meta["type"],
        "name": meta["name"],
        "version": meta["version"],
        "schemaVersion": meta["schemaVersion"],
        "file": gz_path.name,
        "downloadUrl": release_url(repository, tag, gz_path.name),
        "downloadBytes": gz_path.stat().st_size,
        "installedBytes": db_path.stat().st_size,
        "sha256": sha256(gz_path),
    }
    for field in ("city", "networkAsOf", "description", "changes"):
        if field in meta and meta[field] not in (None, "", []):
            descriptor[field] = meta[field]
    return descriptor
