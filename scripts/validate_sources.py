from __future__ import annotations

import argparse
from pathlib import Path

try:
    from .build_all import discover
    from .build_metro import validate_source as validate_metro
    from .build_tv import validate_source as validate_tv
    from .common import ROOT, DataError
except ImportError:
    from build_all import discover
    from build_metro import validate_source as validate_metro
    from build_tv import validate_source as validate_tv
    from common import ROOT, DataError


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate all production source packs without building")
    parser.add_argument("--source", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    count = 0
    ids: set[str] = set()
    for kind, validator in (("metro", validate_metro), ("tv", validate_tv)):
        for folder in discover(args.source, kind):
            data = validator(folder)
            pack_id = data["meta"]["id"]
            if pack_id in ids:
                raise DataError(f"Duplicate global pack id {pack_id!r}")
            ids.add(pack_id)
            count += 1
            print(f"OK {kind}: {pack_id}")
    print(f"Validated {count} production pack(s).")


if __name__ == "__main__":
    try:
        main()
    except DataError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
