from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil

try:
    from .common import DataError, client_data_url, require_string
except ImportError:
    from common import DataError, client_data_url, require_string


def browser_manifest_for_tag(
    release_manifest: dict,
    repository: str,
    tag: str,
    *,
    allow_legacy_v1_urls: bool = False,
) -> dict:
    """Return a browser manifest with immutable URLs for one release tag."""
    if not isinstance(release_manifest, dict):
        raise DataError("release manifest must be an object")
    repository = require_string(repository, "repository")
    tag = require_string(tag, "tag")
    result = copy.deepcopy(release_manifest)
    packs = result.get("packs")
    if not isinstance(packs, list):
        raise DataError("release manifest packs must be an array")
    for pack in packs:
        if not isinstance(pack, dict):
            raise DataError("release manifest pack must be an object")
        filename = require_string(pack.get("file"), "pack.file")
        expected = client_data_url(repository, tag, filename)
        legacy = f"https://github.com/{repository}/releases/download/{tag}/{filename}"
        actual = pack.get("downloadUrl")
        if actual != expected and not (allow_legacy_v1_urls and tag == "v1" and actual == legacy):
            raise DataError(f"unexpected downloadUrl for {filename}: {actual!r}")
        pack["downloadUrl"] = expected
    return result


def root_manifest_applies_to_tag(root_manifest: dict, tag: str) -> bool:
    """Whether a root browser manifest is the manifest for ``tag``."""
    if not isinstance(root_manifest, dict) or not tag.startswith("v"):
        return False
    return root_manifest.get("releaseVersion") == int(tag[1:]) if tag[1:].isdigit() else False


def root_manifest_action(existing: dict | None, candidate: dict) -> str:
    """Choose whether a candidate may replace the latest browser manifest."""
    if not isinstance(candidate, dict) or not isinstance(candidate.get("releaseVersion"), int):
        raise DataError("candidate manifest releaseVersion must be an integer")
    if existing is None:
        return "create"
    if not isinstance(existing, dict) or not isinstance(existing.get("releaseVersion"), int):
        raise DataError("existing root manifest releaseVersion must be an integer")
    if candidate["releaseVersion"] > existing["releaseVersion"]:
        return "update"
    if candidate["releaseVersion"] < existing["releaseVersion"]:
        return "preserve-newer"
    if candidate == existing:
        return "unchanged"
    raise DataError("conflicting manifest for an already-published releaseVersion")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def publish_mirror(
    worktree: Path,
    assets_dir: Path,
    release_manifest: dict,
    repository: str,
    tag: str,
    *,
    allow_legacy_v1_urls: bool = False,
) -> tuple[dict, str, list[str]]:
    """Publish immutable tag assets and monotonically advance the root manifest."""
    candidate = browser_manifest_for_tag(
        release_manifest, repository, tag, allow_legacy_v1_urls=allow_legacy_v1_urls
    )
    if candidate.get("releaseVersion") != int(tag[1:]):
        raise DataError("candidate manifest releaseVersion does not match tag")
    root_path = worktree / "manifest.json"
    existing = json.loads(root_path.read_text(encoding="utf-8")) if root_path.exists() else None
    action = root_manifest_action(existing, candidate)
    tag_dir = worktree / tag
    tag_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for pack in candidate["packs"]:
        filename = pack["file"]
        source = assets_dir / filename
        destination = tag_dir / filename
        if not source.is_file():
            raise DataError(f"missing candidate asset: {source}")
        actual = sha256_file(source)
        if actual != pack.get("sha256"):
            raise DataError(f"candidate checksum mismatch: {filename}")
        if destination.exists():
            if sha256_file(destination) != actual:
                raise DataError(f"immutable client-data asset conflicts: {tag}/{filename}")
        else:
            shutil.copy2(source, destination)
            copied.append(filename)

    if action in {"create", "update"}:
        root_path.write_text(json.dumps(candidate, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return candidate, action, copied


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Create or publish a browser-safe client-data manifest")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path, nargs="?")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--allow-legacy-v1-urls", action="store_true")
    parser.add_argument("--publish-worktree", type=Path)
    parser.add_argument("--assets-dir", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.source.read_text(encoding="utf-8"))
    if args.publish_worktree:
        if args.destination or not args.assets_dir:
            raise SystemExit("ERROR: --publish-worktree requires --assets-dir and no destination")
        _, action, copied = publish_mirror(
            args.publish_worktree, args.assets_dir, manifest, args.repository, args.tag,
            allow_legacy_v1_urls=args.allow_legacy_v1_urls,
        )
        print(f"root manifest: {action}; copied assets: {', '.join(copied) or 'none'}")
        return
    if not args.destination:
        raise SystemExit("ERROR: destination is required without --publish-worktree")
    browser = browser_manifest_for_tag(manifest, args.repository, args.tag,
                                       allow_legacy_v1_urls=args.allow_legacy_v1_urls)
    args.destination.write_text(json.dumps(browser, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except DataError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
