from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

try:
    from .common import ROOT, DataError
except ImportError:
    from common import ROOT, DataError


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an empty production source-pack folder")
    parser.add_argument("type", choices=["metro", "tv"])
    parser.add_argument("--id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--city")
    parser.add_argument("--network-as-of")
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()

    if args.type == "metro" and (not args.city or not args.network_as_of):
        raise DataError("Metro scaffold requires --city and --network-as-of")

    template = ROOT / "templates" / ("metro-city" if args.type == "metro" else "tv")
    if args.destination:
        destination = args.destination
    else:
        folder_name = args.id.removeprefix("metro-") if args.type == "metro" else args.id
        destination = ROOT / "data" / args.type / folder_name
    if destination.exists():
        raise DataError(f"Destination already exists: {destination}")
    shutil.copytree(template, destination)

    meta_path = destination / "pack.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["id"] = args.id
    meta["name"] = args.name
    if args.type == "metro":
        meta["city"] = args.city
        meta["networkAsOf"] = args.network_as_of
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    try:
        main()
    except DataError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
