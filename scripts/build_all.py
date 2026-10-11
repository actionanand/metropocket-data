from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

try:
    from .build_metro import build_pack as build_metro
    from .build_tv import build_pack as build_tv
    from .common import ROOT, DataError, load_json, require_positive_int, utc_now_iso
except ImportError:
    from build_metro import build_pack as build_metro
    from build_tv import build_pack as build_tv
    from common import ROOT, DataError, load_json, require_positive_int, utc_now_iso


def discover(source: Path, kind: str) -> list[Path]:
    base = source / kind
    if not base.exists():
        return []
    return sorted(path.parent for path in base.glob("*/pack.json"))


def build_all(
    source: Path,
    output: Path,
    repository: str,
    tag: str,
    release_version: int | None = None,
    require_packs: bool = False,
) -> dict:
    release = load_json(ROOT / "release.json")
    if not isinstance(release, dict) or release.get("schemaVersion") != 1:
        raise DataError("release.json schemaVersion must be 1")
    version = release_version if release_version is not None else release.get("releaseVersion")
    require_positive_int(version, "releaseVersion")

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    descriptors = []
    for folder in discover(source, "metro"):
        descriptors.append(build_metro(folder, output, repository, tag))
    for folder in discover(source, "tv"):
        descriptors.append(build_tv(folder, output, repository, tag))
    if require_packs and not descriptors:
        raise DataError("No production packs found; refusing to create a release")

    ids = [item["id"] for item in descriptors]
    if len(ids) != len(set(ids)):
        raise DataError("Pack ids must be globally unique across metro and tv packs")

    manifest = {
        "schemaVersion": 1,
        "releaseVersion": version,
        "generatedAt": utc_now_iso(),
        "packs": descriptors,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build all MetroPocket data packs")
    parser.add_argument("--source", type=Path, default=ROOT / "data")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--repository", default="actionanand/metropocket-data")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--release-version", type=int)
    parser.add_argument("--require-packs", action="store_true")
    args = parser.parse_args()
    manifest = build_all(
        args.source, args.output, args.repository, args.tag, args.release_version, args.require_packs
    )
    print(f"Built {len(manifest['packs'])} pack(s) -> {args.output}")
    print(f"Manifest releaseVersion={manifest['releaseVersion']}")


if __name__ == "__main__":
    try:
        main()
    except DataError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
