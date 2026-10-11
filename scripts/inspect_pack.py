from __future__ import annotations

import argparse
import gzip
import os
import sqlite3
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a generated .db or .db.gz pack")
    parser.add_argument("pack", type=Path)
    args = parser.parse_args()
    source = args.pack
    temp_name = None
    try:
        if source.suffix == ".gz":
            with gzip.open(source, "rb") as src, tempfile.NamedTemporaryFile(delete=False, suffix=".db") as dst:
                dst.write(src.read())
                temp_name = dst.name
            db = Path(temp_name)
        else:
            db = source
        connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            metadata = dict(connection.execute("SELECT key,value FROM metadata ORDER BY key").fetchall())
            print("Metadata:")
            for key, value in metadata.items():
                print(f"  {key}: {value}")
            print("Tables:")
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            for table in tables:
                count = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                print(f"  {table}: {count}")
        finally:
            connection.close()
    finally:
        if temp_name:
            os.unlink(temp_name)


if __name__ == "__main__":
    main()
