"""Print a compact, reproducible coverage report for the generated TV pack."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

try:
    from .common import ROOT
    from .import_tv_channels import (
        AIRTEL_REVISION,
        EXTERNAL_REVISION,
        OBSERVED_REVISION,
        SNAPSHOT_DATE,
        _check_observed,
        apply_airtel_scope_metadata,
        read_rows,
        resolve_airtel_official,
        resolve_jio_external,
    )
except ImportError:
    from common import ROOT
    from import_tv_channels import (
        AIRTEL_REVISION,
        EXTERNAL_REVISION,
        OBSERVED_REVISION,
        SNAPSHOT_DATE,
        _check_observed,
        apply_airtel_scope_metadata,
        read_rows,
        resolve_airtel_official,
        resolve_jio_external,
    )


def print_counts(title: str, values: Counter[str]) -> None:
    print(title)
    for key in sorted(values, key=lambda item: (item == "", item.casefold())):
        print(f"  {key or 'unknown'}: {values[key]}")


def print_provider_metadata(provider_id: str, mappings: list[dict[str, str]], channels: dict[str, dict[str, str]]) -> None:
    scoped = [row for row in mappings if row["provider_id"] == provider_id]
    metadata = [channels[row["channel_id"]] for row in scoped]
    print(f"{provider_id} metadata completeness:")
    print(f"  total mappings: {len(scoped)}")
    for field in ("language", "genre", "quality"):
        known = sum(bool(row[field]) for row in metadata)
        print(f"  {field}: known {known}; unknown {len(metadata) - known}")
        print_counts(f"  {field} distribution:", Counter(row[field] for row in metadata))


def main() -> None:
    parser = argparse.ArgumentParser(description="Report the current checked-in TV channel pack")
    parser.add_argument("--pack-dir", type=Path, default=ROOT / "data" / "tv" / "tv-channels")
    parser.add_argument("--sources", type=Path, default=ROOT / "sources" / "tv")
    args = parser.parse_args()
    channels = read_rows(args.pack_dir / "channels.csv", ("id", "language", "genre", "quality"))
    aliases = read_rows(args.pack_dir / "channel_aliases.csv", ("channel_id", "alias"))
    mappings = read_rows(args.pack_dir / "provider_channels.csv", ("provider_id", "channel_id", "revision"))
    providers = read_rows(args.pack_dir / "providers.csv", ("id", "kind"))
    observed = read_rows(args.sources / "jiotv-plus" / f"user-observed-{SNAPSHOT_DATE}.csv", ("number", "name", "native_name", "language", "genre"))
    external = read_rows(args.sources / "jiotv-plus" / f"external-{SNAPSHOT_DATE}.csv", ("number", "name", "language", "genre", "quality", "source_url", "retrieved_at"))
    jio_conflicts = read_rows(args.sources / "jiotv-plus" / f"conflicts-{SNAPSHOT_DATE}.csv", ("number", "reason"))
    airtel = apply_airtel_scope_metadata(read_rows(args.sources / "airtel-digital-tv" / f"official-{SNAPSHOT_DATE}.csv", ("number", "name", "language", "genre", "quality", "source_url", "verified_at")))
    _, external_metrics = resolve_jio_external(external, _check_observed(observed))
    _, _, airtel_metrics = resolve_airtel_official(airtel)
    mapping_counts = Counter(row["provider_id"] for row in mappings)
    revision_counts = Counter(row["revision"] for row in mappings)
    channels_by_id = {row["id"]: row for row in channels}

    print(f"Total canonical channels: {len(channels)}")
    print(f"Total aliases: {len(aliases)}")
    print(f"Total provider mappings: {len(mappings)}")
    print("JioTV+:")
    print(f"  total: {mapping_counts['jiotv-plus']}")
    print(f"  subscriber-observed: {revision_counts[OBSERVED_REVISION]}")
    print(f"  external retained: {revision_counts[EXTERNAL_REVISION]}")
    print(f"  conflicts overridden: {external_metrics['jio_conflicts_overridden']}")
    print(f"  conflicts excluded: {external_metrics['jio_conflicts_excluded']}")
    print(f"  ranges excluded: {sum('range without individual identities' in row['reason'] for row in jio_conflicts)}")
    print("Airtel Digital TV:")
    print(f"  total final mappings: {revision_counts[AIRTEL_REVISION]}")
    print(f"  official rows considered: {airtel_metrics['airtel_official_rows_considered']}")
    print(f"  duplicate rows collapsed: {airtel_metrics['airtel_duplicate_rows_collapsed']}")
    print(f"  aggregate conflicts resolved by dedicated pages: {airtel_metrics['airtel_aggregate_conflicts_resolved']}")
    print(f"  unresolved conflicts excluded: {airtel_metrics['airtel_conflicts_excluded']}")
    print_counts("Counts by provider:", mapping_counts)
    print_counts("Counts by language:", Counter(row["language"] for row in channels))
    print_counts("Counts by genre:", Counter(row["genre"] for row in channels))
    print_counts("Counts by quality:", Counter(row["quality"] for row in channels))
    print("Unknown:")
    print(f"  language: {sum(not row['language'] for row in channels)}")
    print(f"  genre: {sum(not row['genre'] for row in channels)}")
    print(f"  quality: {sum(not row['quality'] for row in channels)}")
    print_counts("Provider kinds:", Counter(row["kind"] for row in providers))
    for provider in providers:
        print_provider_metadata(provider["id"], mappings, channels_by_id)


if __name__ == "__main__":
    main()
