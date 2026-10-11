from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any

try:
    from .common import (
        ROOT,
        SCHEMAS,
        STATUS_VALUES,
        DataError,
        deterministic_gzip,
        load_pack_meta,
        open_database,
        pack_descriptor,
        parse_bool01,
        parse_float,
        parse_int,
        put_metadata,
        read_csv,
        require_string,
        unique_ids,
    )
except ImportError:
    from common import (
        ROOT,
        SCHEMAS,
        STATUS_VALUES,
        DataError,
        deterministic_gzip,
        load_pack_meta,
        open_database,
        pack_descriptor,
        parse_bool01,
        parse_float,
        parse_int,
        put_metadata,
        read_csv,
        require_string,
        unique_ids,
    )


def _status(row: dict[str, str], label: str) -> str:
    value = require_string(row.get("status"), f"{label}.status")
    if value not in STATUS_VALUES:
        raise DataError(f"{label}.status must be one of {sorted(STATUS_VALUES)}")
    return value


def validate_source(folder: Path) -> dict[str, Any]:
    meta = load_pack_meta(folder, "metro")
    require_string(meta.get("city"), "city")
    require_string(meta.get("networkAsOf"), "networkAsOf")
    default_edge = meta.get("defaultEdgeMinutes", 3)
    if not isinstance(default_edge, (int, float)) or isinstance(default_edge, bool) or default_edge <= 0:
        raise DataError("defaultEdgeMinutes must be a positive number")

    stations = read_csv(folder / "stations.csv", ["id", "name", "status", "latitude", "longitude"])
    aliases = read_csv(folder / "station_aliases.csv", ["station_id", "alias"])
    codes = read_csv(folder / "station_codes.csv", ["station_id", "code"])
    lines = read_csv(
        folder / "lines.csv",
        ["id", "name", "short_name", "color", "status", "terminal_a_station_id", "terminal_b_station_id"],
    )
    station_lines = read_csv(folder / "station_lines.csv", ["station_id", "line_id", "sequence"])
    connections = read_csv(
        folder / "connections.csv",
        ["from_station_id", "to_station_id", "line_id", "travel_minutes", "status", "bidirectional"],
    )
    interchanges = read_csv(
        folder / "interchanges.csv", ["station_id", "from_line_id", "to_line_id", "walk_minutes"]
    )

    if not stations:
        raise DataError(f"{folder}: a Metro pack must contain at least one station")
    if not lines:
        raise DataError(f"{folder}: a Metro pack must contain at least one line")

    station_ids = unique_ids(stations, "id", "station")
    line_ids = unique_ids(lines, "id", "line")

    for row in stations:
        require_string(row["name"], "station.name")
        _status(row, "station")
        lat = parse_float(row["latitude"], "station.latitude", allow_blank=True)
        lon = parse_float(row["longitude"], "station.longitude", allow_blank=True)
        if lat is not None and not -90 <= lat <= 90:
            raise DataError("station.latitude must be between -90 and 90")
        if lon is not None and not -180 <= lon <= 180:
            raise DataError("station.longitude must be between -180 and 180")

    for row in lines:
        require_string(row["name"], "line.name")
        color = require_string(row["color"], "line.color")
        if not (len(color) == 7 and color.startswith("#") and all(c in "0123456789abcdefABCDEF" for c in color[1:])):
            raise DataError(f"line.color must be #RRGGBB, got {color!r}")
        _status(row, "line")
        for terminal_field in ("terminal_a_station_id", "terminal_b_station_id"):
            terminal = row[terminal_field]
            if terminal and terminal not in station_ids:
                raise DataError(f"{terminal_field} references unknown station {terminal!r}")

    for row in aliases:
        if row["station_id"] not in station_ids:
            raise DataError(f"station alias references unknown station {row['station_id']!r}")
        require_string(row["alias"], "station alias")

    for row in codes:
        if row["station_id"] not in station_ids:
            raise DataError(f"station code references unknown station {row['station_id']!r}")
        require_string(row["code"], "station code")

    seen_memberships: set[tuple[str, str]] = set()
    seen_sequences: set[tuple[str, int]] = set()
    memberships: set[tuple[str, str]] = set()
    for row in station_lines:
        station_id, line_id = row["station_id"], row["line_id"]
        if station_id not in station_ids or line_id not in line_ids:
            raise DataError(f"station_lines contains unknown station/line: {station_id!r}, {line_id!r}")
        sequence = parse_int(row["sequence"], "station_lines.sequence", minimum=0)
        assert sequence is not None
        membership = (station_id, line_id)
        if membership in seen_memberships:
            raise DataError(f"Duplicate station-line membership {membership}")
        if (line_id, sequence) in seen_sequences:
            raise DataError(f"Duplicate sequence {sequence} on line {line_id}")
        seen_memberships.add(membership)
        seen_sequences.add((line_id, sequence))
        memberships.add(membership)

    for row in connections:
        a, b, line_id = row["from_station_id"], row["to_station_id"], row["line_id"]
        if a not in station_ids or b not in station_ids:
            raise DataError(f"connection references unknown station: {a!r}->{b!r}")
        if a == b:
            raise DataError("connection cannot connect a station to itself")
        if line_id not in line_ids:
            raise DataError(f"connection references unknown line {line_id!r}")
        if (a, line_id) not in memberships or (b, line_id) not in memberships:
            raise DataError(f"connection stations must both belong to line {line_id!r}")
        parse_float(row["travel_minutes"], "connection.travel_minutes", allow_blank=True, minimum=0)
        _status(row, "connection")
        parse_bool01(row["bidirectional"], "connection.bidirectional")

    seen_interchanges: set[tuple[str, str, str]] = set()
    for row in interchanges:
        station, from_line, to_line = row["station_id"], row["from_line_id"], row["to_line_id"]
        if station not in station_ids or from_line not in line_ids or to_line not in line_ids:
            raise DataError("interchange references an unknown station or line")
        if from_line == to_line:
            raise DataError("interchange lines must be different")
        if (station, from_line) not in memberships or (station, to_line) not in memberships:
            raise DataError("interchange station must belong to both lines")
        key = (station, from_line, to_line)
        reverse = (station, to_line, from_line)
        if key in seen_interchanges or reverse in seen_interchanges:
            raise DataError(f"Duplicate interchange {key}")
        seen_interchanges.add(key)
        parse_float(row["walk_minutes"], "interchange.walk_minutes", allow_blank=True, minimum=0)

    return {
        "meta": meta,
        "stations": stations,
        "aliases": aliases,
        "codes": codes,
        "lines": lines,
        "station_lines": station_lines,
        "connections": connections,
        "interchanges": interchanges,
    }


def build_pack(folder: Path, output: Path, repository: str, tag: str) -> dict[str, Any]:
    data = validate_source(folder)
    meta = data["meta"]
    output.mkdir(parents=True, exist_ok=True)
    db_path = output / f"{meta['id']}.db"
    gz_path = output / f"{meta['id']}.db.gz"
    connection = open_database(db_path, SCHEMAS / "metro.sql")
    try:
        put_metadata(
            connection,
            {
                "packId": meta["id"],
                "type": "metro",
                "name": meta["name"],
                "version": meta["version"],
                "schemaVersion": meta["schemaVersion"],
                "city": meta["city"],
                "networkAsOf": meta["networkAsOf"],
                "defaultEdgeMinutes": meta.get("defaultEdgeMinutes", 3),
            },
        )
        connection.executemany(
            "INSERT INTO stations(id,name,status,latitude,longitude) VALUES (?,?,?,?,?)",
            [
                (
                    row["id"],
                    row["name"],
                    row["status"],
                    parse_float(row["latitude"], "station.latitude", True),
                    parse_float(row["longitude"], "station.longitude", True),
                )
                for row in data["stations"]
            ],
        )
        connection.executemany(
            "INSERT INTO lines(id,name,short_name,color,status,terminal_a_station_id,terminal_b_station_id) VALUES (?,?,?,?,?,?,?)",
            [
                (
                    row["id"],
                    row["name"],
                    row["short_name"] or None,
                    row["color"],
                    row["status"],
                    row["terminal_a_station_id"] or None,
                    row["terminal_b_station_id"] or None,
                )
                for row in data["lines"]
            ],
        )
        connection.executemany(
            "INSERT INTO station_aliases(station_id,alias) VALUES (?,?)",
            [(row["station_id"], row["alias"]) for row in data["aliases"]],
        )
        connection.executemany(
            "INSERT INTO station_codes(station_id,code) VALUES (?,?)",
            [(row["station_id"], row["code"]) for row in data["codes"]],
        )
        connection.executemany(
            "INSERT INTO station_lines(station_id,line_id,sequence) VALUES (?,?,?)",
            [
                (row["station_id"], row["line_id"], parse_int(row["sequence"], "station_lines.sequence", minimum=0))
                for row in data["station_lines"]
            ],
        )
        connection.executemany(
            """INSERT INTO connections(
              from_station_id,to_station_id,line_id,travel_minutes,status,bidirectional
            ) VALUES (?,?,?,?,?,?)""",
            [
                (
                    row["from_station_id"],
                    row["to_station_id"],
                    row["line_id"],
                    parse_float(row["travel_minutes"], "connection.travel_minutes", True, 0),
                    row["status"],
                    parse_bool01(row["bidirectional"], "connection.bidirectional"),
                )
                for row in data["connections"]
            ],
        )
        connection.executemany(
            "INSERT INTO interchanges(station_id,from_line_id,to_line_id,walk_minutes) VALUES (?,?,?,?)",
            [
                (
                    row["station_id"],
                    row["from_line_id"],
                    row["to_line_id"],
                    parse_float(row["walk_minutes"], "interchange.walk_minutes", True, 0),
                )
                for row in data["interchanges"]
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
    parser = argparse.ArgumentParser(description="Build one Metro SQLite pack")
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
