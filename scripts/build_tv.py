from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any

try:
    from .common import (
        ROOT,
        SCHEMAS,
        DataError,
        deterministic_gzip,
        load_json,
        load_pack_meta,
        open_database,
        pack_descriptor,
        put_metadata,
        read_csv,
        require_string,
        unique_ids,
    )
except ImportError:
    from common import (
        ROOT,
        SCHEMAS,
        DataError,
        deterministic_gzip,
        load_json,
        load_pack_meta,
        open_database,
        pack_descriptor,
        put_metadata,
        read_csv,
        require_string,
        unique_ids,
    )


def validate_source(folder: Path) -> dict[str, Any]:
    meta = load_pack_meta(folder, "tv")
    providers = read_csv(folder / "providers.csv", ["id", "name", "kind"])
    channels = read_csv(folder / "channels.csv", ["id", "name", "language", "genre", "quality"])
    aliases = read_csv(folder / "channel_aliases.csv", ["channel_id", "alias"])
    mappings = read_csv(
        folder / "provider_channels.csv",
        ["provider_id", "channel_id", "number", "country", "state", "city", "area", "revision", "verified_at", "source_url"],
    )
    if not providers:
        raise DataError(f"{folder}: a TV pack must contain at least one provider")
    if not channels:
        raise DataError(f"{folder}: a TV pack must contain at least one channel")

    provider_ids = unique_ids(providers, "id", "provider")
    channel_ids = unique_ids(channels, "id", "channel")

    canonical = {item["id"]: item for item in load_json(ROOT / "config" / "tv-providers.json")}
    for row in providers:
        require_string(row["name"], "provider.name")
        if row["kind"] not in {"dth", "cable", "iptv"}:
            raise DataError("provider.kind must be dth, cable or iptv")
        if row["id"] not in canonical:
            raise DataError(f"Unknown provider id {row['id']!r}; update config/tv-providers.json deliberately first")
        if canonical[row["id"]]["kind"] != row["kind"]:
            raise DataError(f"Provider kind mismatch for {row['id']!r}")

    for row in channels:
        require_string(row["name"], "channel.name")
        if row["quality"] not in {"", "SD", "HD", "4K"}:
            raise DataError("channel.quality must be SD, HD, 4K or blank")

    for row in aliases:
        if row["channel_id"] not in channel_ids:
            raise DataError(f"channel alias references unknown channel {row['channel_id']!r}")
        require_string(row["alias"], "channel alias")

    seen: set[tuple[str, ...]] = set()
    national_numbers: dict[tuple[str, str], str] = {}
    for row in mappings:
        if row["provider_id"] not in provider_ids:
            raise DataError(f"mapping references unknown provider {row['provider_id']!r}")
        if row["channel_id"] not in channel_ids:
            raise DataError(f"mapping references unknown channel {row['channel_id']!r}")
        require_string(row["number"], "mapping.number")
        if row["source_url"] and not row["source_url"].startswith("https://"):
            raise DataError("mapping.source_url must be HTTPS when supplied")
        key = (
            row["provider_id"],
            row["channel_id"],
            row["number"],
            row["country"],
            row["state"],
            row["city"],
            row["area"],
            row["revision"],
        )
        if key in seen:
            raise DataError(f"Duplicate provider mapping {key}")
        seen.add(key)
        if row["provider_id"] in {"jiotv-plus", "airtel-digital-tv"}:
            number_key = (row["provider_id"], row["number"])
            existing_channel = national_numbers.get(number_key)
            if existing_channel and existing_channel != row["channel_id"]:
                raise DataError(f"Conflicting national provider channel number {number_key}")
            national_numbers[number_key] = row["channel_id"]

    return {"meta": meta, "providers": providers, "channels": channels, "aliases": aliases, "mappings": mappings}


def build_pack(folder: Path, output: Path, repository: str, tag: str) -> dict[str, Any]:
    data = validate_source(folder)
    meta = data["meta"]
    output.mkdir(parents=True, exist_ok=True)
    db_path = output / f"{meta['id']}.db"
    gz_path = output / f"{meta['id']}.db.gz"
    connection = open_database(db_path, SCHEMAS / "tv.sql")
    try:
        put_metadata(
            connection,
            {
                "packId": meta["id"],
                "type": "tv",
                "name": meta["name"],
                "version": meta["version"],
                "schemaVersion": meta["schemaVersion"],
            },
        )
        connection.executemany(
            "INSERT INTO providers(id,name,kind) VALUES (?,?,?)",
            [(row["id"], row["name"], row["kind"]) for row in data["providers"]],
        )
        connection.executemany(
            "INSERT INTO channels(id,name,language,genre,quality) VALUES (?,?,?,?,?)",
            [
                (
                    row["id"],
                    row["name"],
                    row["language"] or None,
                    row["genre"] or None,
                    row["quality"] or None,
                )
                for row in data["channels"]
            ],
        )
        connection.executemany(
            "INSERT INTO channel_aliases(channel_id,alias) VALUES (?,?)",
            [(row["channel_id"], row["alias"]) for row in data["aliases"]],
        )
        connection.executemany(
            """INSERT INTO provider_channels(
              provider_id,channel_id,number,country,state,city,area,revision,verified_at,source_url
            ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    row["provider_id"],
                    row["channel_id"],
                    row["number"],
                    row["country"] or None,
                    row["state"] or None,
                    row["city"] or None,
                    row["area"] or None,
                    row["revision"] or None,
                    row["verified_at"] or None,
                    row["source_url"] or None,
                )
                for row in data["mappings"]
            ],
        )
        connection.commit()
        problems = connection.execute("PRAGMA foreign_key_check").fetchall()
        if problems:
            raise DataError(f"foreign key validation failed: {problems}")
        connection.execute("VACUUM")
    finally:
        connection.close()

    deterministic_gzip(db_path, gz_path)
    descriptor = pack_descriptor(meta, db_path, gz_path, repository, tag)
    db_path.unlink()
    return descriptor


def main() -> None:
    parser = argparse.ArgumentParser(description="Build one TV SQLite pack")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--repository", default="actionanand/metropocket-data")
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    descriptor = build_pack(args.folder, args.output, args.repository, args.tag)
    print(descriptor)


if __name__ == "__main__":
    try:
        main()
    except (DataError, sqlite3.Error) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
