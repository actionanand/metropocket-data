"""Deterministically generate the TV pack from dated factual snapshots."""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import tempfile
import unicodedata
from collections import defaultdict
from pathlib import Path

try:
    from .common import ROOT, DataError
except ImportError:
    from common import ROOT, DataError


SNAPSHOT_DATE = "2026-10-12"
OBSERVED_REVISION = f"subscriber-observed-{SNAPSHOT_DATE}"
EXTERNAL_REVISION = f"techiga-external-{SNAPSHOT_DATE}"
AIRTEL_REVISION = f"airtel-official-{SNAPSHOT_DATE}"
AIRTEL_URL = "https://www.airtel.in/plans/dth/all-channel-list"
JIO_URL = "https://techiga.com/jiotv-plus-complete-live-tv-channel-list/"
NUMBER_RE = re.compile(r"^\d+$")


def clean(value: str) -> str:
    return " ".join((value or "").replace("\xa0", " ").split())


def slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    result = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return result or "channel-" + hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]


def read_rows(path: Path, required: tuple[str, ...] = ()) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [field for field in required if field not in set(reader.fieldnames or [])]
        if missing:
            raise DataError(f"{path}: missing CSV columns: {', '.join(missing)}")
        return [{key: clean(value or "") for key, value in row.items() if key is not None} for row in reader]


def write_rows(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def normalize_language(value: str) -> str:
    value = clean(value)
    aliases = {"oriya": "Odia", "odia": "Odia"}
    known = {"assamese", "bengali", "bhojpuri", "english", "gujarati", "hindi", "kannada", "malayalam", "marathi", "punjabi", "tamil", "telugu", "urdu"}
    # Airtel accordion labels use a trailing plus to indicate a combined group
    # (for example, "Assamese +"); it is not part of the filter value.
    decorated = re.sub(r"\s*\+\s*$", "", value).strip()
    if decorated.casefold() in known or decorated.casefold() in aliases:
        value = decorated
    return aliases.get(value.casefold(), value.title() if value.casefold() in known else value)


def normalize_genre(value: str) -> str:
    value = clean(value)
    lowered = value.casefold()
    if not lowered:
        return ""
    # The controlled vocabulary intentionally rejects source language headings
    # that sometimes occupy Airtel's category field on scoped pages.
    if lowered in {"assamese", "bengali", "bhojpuri", "english", "gujarati", "hindi", "kannada", "malayalam", "marathi", "odia", "oriya", "punjabi", "tamil", "telugu", "urdu"}:
        return ""
    labels = (("business", "Business"), ("news", "News"), ("movie", "Movies"), ("sport", "Sports"), ("music", "Music"),
              ("kid", "Kids"), ("devotional", "Devotional"), ("relig", "Devotional"),
              ("infotain", "Infotainment"), ("documentary", "Infotainment"), ("lifestyle", "Lifestyle"),
              ("entertain", "Entertainment"), ("general", "Entertainment"),
              ("gec", "Entertainment"), ("educat", "Education"), ("shopping", "Shopping"),
              ("international", "International"), ("regional", "Regional"))
    for needle, label in labels:
        if needle in lowered:
            return label
    return "Other" if lowered in {"other", "others", "fta", "misc"} else ""


def normalize_quality(value: str) -> str:
    labels = {label.upper() for label in re.findall(r"\b(?:SD|HD|4K)\b", value, re.I)}
    return "4K" if "4K" in labels else "HD" if "HD" in labels else "SD" if "SD" in labels else ""


def normalized_name(value: str) -> str:
    """Compare provider labels without making an unsupported display-name edit."""
    return re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKD", clean(value)).encode("ascii", "ignore").decode("ascii").casefold())


def is_dedicated_airtel(row: dict[str, str]) -> bool:
    return row.get("source_scope", "aggregate") != "aggregate"


def apply_airtel_scope_metadata(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Fill a blank language only when an official dedicated URL states it."""
    enriched = []
    for row in rows:
        copy = dict(row)
        scope = copy.get("source_scope", "")
        if not copy.get("language") and scope.startswith("language:"):
            copy["language"] = scope.split(":", 1)[1]
        enriched.append(copy)
    return enriched


def resolve_airtel_official(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, int]]:
    """Resolve one national Airtel number using only its official provenance.

    Dedicated language/category pages take precedence over the broad aggregate
    page.  Conflicting dedicated evidence is intentionally excluded.
    """
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if NUMBER_RE.fullmatch(row.get("number", "")) and row.get("name"):
            grouped[row["number"]].append(row)
    retained: list[dict[str, str]] = []
    reports: list[dict[str, str]] = []
    metrics = {
        "airtel_official_rows_considered": sum(len(values) for values in grouped.values()),
        "airtel_duplicate_rows_collapsed": 0,
        "airtel_aggregate_conflicts_resolved": 0,
        "airtel_conflicts_excluded": 0,
    }
    for number in sorted(grouped, key=int):
        candidates = grouped[number]
        unique_facts: dict[str, dict[str, str]] = {}
        for row in candidates:
            # For a provider number, repeated spelling-identical services from
            # several official pages are duplicates even when a scoped page
            # supplies richer language/category metadata.
            key = normalized_name(row["name"])
            existing = unique_facts.get(key)
            if existing is None or (is_dedicated_airtel(row) and not is_dedicated_airtel(existing)):
                unique_facts[key] = row
        metrics["airtel_duplicate_rows_collapsed"] += len(candidates) - len(unique_facts)
        distinct_names = {normalized_name(row["name"]) for row in unique_facts.values()}
        dedicated = [row for row in candidates if is_dedicated_airtel(row)]
        dedicated_names = {normalized_name(row["name"]) for row in dedicated}
        aggregate_names = sorted({row["name"] for row in unique_facts.values() if not is_dedicated_airtel(row)}, key=str.casefold)
        dedicated_labels = sorted({row["name"] for row in dedicated}, key=str.casefold)
        if len(distinct_names) == 1:
            # Prefer a dedicated provenance row when it states the same channel.
            chosen = sorted(dedicated or list(unique_facts.values()), key=lambda row: (row.get("source_url", ""), row["name"].casefold()))[0]
            retained.append(chosen)
            continue
        if len(dedicated_names) == 1:
            chosen = sorted(dedicated, key=lambda row: (row.get("source_url", ""), row["name"].casefold()))[0]
            retained.append(chosen)
            metrics["airtel_aggregate_conflicts_resolved"] += 1
            reports.append({"number": number, "aggregate_names": " | ".join(aggregate_names),
                            "dedicated_names": " | ".join(dedicated_labels), "chosen_name": chosen["name"],
                            "chosen_source_url": chosen.get("source_url", ""), "resolution": "dedicated official page selected",
                            "reason": "aggregate mapping conflicts; dedicated official evidence is unambiguous"})
        else:
            metrics["airtel_conflicts_excluded"] += 1
            reports.append({"number": number, "aggregate_names": " | ".join(aggregate_names),
                            "dedicated_names": " | ".join(dedicated_labels), "chosen_name": "", "chosen_source_url": "",
                            "resolution": "excluded", "reason": "official sources do not resolve one channel for this provider number"})
    return retained, reports, metrics


def _check_observed(observed: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    if len(observed) != 72:
        raise DataError(f"Expected exactly 72 subscriber-observed rows, got {len(observed)}")
    indexed: dict[str, dict[str, str]] = {}
    for row in observed:
        if not NUMBER_RE.fullmatch(row.get("number", "")) or not row.get("name") or not row.get("native_name"):
            raise DataError("Subscriber-observed rows require a numeric number, English name and native name")
        if row["number"] in indexed:
            raise DataError(f"Duplicate subscriber-observed number {row['number']}")
        indexed[row["number"]] = row
    return indexed


def resolve_jio_external(external: list[dict[str, str]], observed: dict[str, dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Keep unambiguous external rows; observations replace every same-number row."""
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in external:
        if NUMBER_RE.fullmatch(row.get("number", "")) and row.get("name"):
            grouped[row["number"]].append(row)
    retained: list[dict[str, str]] = []
    metrics = {"jio_external_retained": 0, "jio_conflicts_overridden": 0, "jio_conflicts_excluded": 0}
    for number in sorted(grouped, key=int):
        rows = grouped[number]
        unique = {clean(row["name"]).casefold(): row for row in rows}
        if number in observed:
            metrics["jio_conflicts_overridden"] += 1
        elif len(unique) > 1:
            metrics["jio_conflicts_excluded"] += 1
        else:
            retained.append(next(iter(unique.values())))
            metrics["jio_external_retained"] += 1
    return retained, metrics


class ChannelCatalog:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, str]] = {}
        self.priority: dict[tuple[str, str], int] = {}
        self.aliases: set[tuple[str, str]] = set()

    def add(self, name: str, language: str, genre: str, quality: str, *, priority: int, native_alias: str = "") -> str:
        name = clean(name)
        channel_id = slug(name)
        candidate = {"id": channel_id, "name": name, "language": normalize_language(language),
                     "genre": normalize_genre(genre), "quality": normalize_quality(quality)}
        current = self.rows.get(channel_id)
        if current is None:
            self.rows[channel_id] = candidate
            for field in ("language", "genre", "quality"):
                if candidate[field]:
                    self.priority[(channel_id, field)] = priority
        else:
            for field in ("language", "genre", "quality"):
                if candidate[field] and priority >= self.priority.get((channel_id, field), -1):
                    current[field] = candidate[field]
                    self.priority[(channel_id, field)] = priority
        native_alias = clean(native_alias)
        if native_alias and native_alias != name:
            self.aliases.add((channel_id, native_alias))
        return channel_id


def generate(pack_dir: Path, sources: Path) -> dict[str, int]:
    observed = read_rows(sources / "jiotv-plus" / f"user-observed-{SNAPSHOT_DATE}.csv", ("number", "name", "native_name", "language", "genre"))
    observed_by_number = _check_observed(observed)
    external = read_rows(sources / "jiotv-plus" / f"external-{SNAPSHOT_DATE}.csv", ("number", "name", "language", "genre", "quality", "source_url", "retrieved_at"))
    airtel = apply_airtel_scope_metadata(read_rows(sources / "airtel-digital-tv" / f"official-{SNAPSHOT_DATE}.csv", ("number", "name", "language", "genre", "quality", "source_url", "verified_at")))
    external, metrics = resolve_jio_external(external, observed_by_number)
    airtel, _, airtel_metrics = resolve_airtel_official(airtel)
    catalog = ChannelCatalog()
    mappings: list[dict[str, str]] = []
    seen_mapping_numbers: set[tuple[str, str]] = set()

    def add_mapping(provider_id: str, row: dict[str, str], *, revision: str, verified_at: str, source_url: str, priority: int, native_alias: str = "") -> None:
        number = row["number"]
        if not NUMBER_RE.fullmatch(number):
            raise DataError(f"{provider_id}: non-numeric channel number {number!r}")
        key = (provider_id, number)
        if key in seen_mapping_numbers:
            raise DataError(f"Duplicate resolved {provider_id} channel number {number}")
        seen_mapping_numbers.add(key)
        channel_id = catalog.add(row["name"], row.get("language", ""), row.get("genre", ""), row.get("quality", ""), priority=priority, native_alias=native_alias)
        mappings.append({"provider_id": provider_id, "channel_id": channel_id, "number": number,
                         "country": "IN", "state": "", "city": "", "area": "", "revision": revision,
                         "verified_at": verified_at, "source_url": source_url})

    for row in external:
        add_mapping("jiotv-plus", row, revision=EXTERNAL_REVISION, verified_at=row.get("retrieved_at", SNAPSHOT_DATE), source_url=row.get("source_url", JIO_URL), priority=1)
    for row in observed:
        add_mapping("jiotv-plus", row, revision=OBSERVED_REVISION, verified_at=SNAPSHOT_DATE, source_url="", priority=2, native_alias=row["native_name"])
    for row in sorted(airtel, key=lambda item: (int(item["number"]) if NUMBER_RE.fullmatch(item["number"]) else -1, item["name"].casefold())):
        add_mapping("airtel-digital-tv", row, revision=AIRTEL_REVISION, verified_at=row.get("verified_at", SNAPSHOT_DATE), source_url=row.get("source_url", AIRTEL_URL), priority=1)

    providers = [{"id": "jiotv-plus", "name": "JioTV+", "kind": "iptv"}, {"id": "airtel-digital-tv", "name": "Airtel Digital TV", "kind": "dth"}]
    channels = sorted(catalog.rows.values(), key=lambda item: item["id"])
    aliases = [{"channel_id": channel_id, "alias": alias} for channel_id, alias in sorted(catalog.aliases)]
    provider_order = {"jiotv-plus": 0, "airtel-digital-tv": 1}
    mapping_rows = sorted(mappings, key=lambda item: (provider_order[item["provider_id"]], int(item["number"]), item["channel_id"]))
    # Stage and validate all replacements before touching the checked-in pack.
    pack_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".tv-import-", dir=pack_dir.parent) as temporary:
        staged = Path(temporary)
        write_rows(staged / "providers.csv", ["id", "name", "kind"], providers)
        write_rows(staged / "channels.csv", ["id", "name", "language", "genre", "quality"], channels)
        write_rows(staged / "channel_aliases.csv", ["channel_id", "alias"], aliases)
        write_rows(staged / "provider_channels.csv", ["provider_id", "channel_id", "number", "country", "state", "city", "area", "revision", "verified_at", "source_url"], mapping_rows)
        # The resolver guarantees national provider-number uniqueness; assert it
        # before any replacement so a regression cannot leave partial output.
        if len({(row["provider_id"], row["number"]) for row in mapping_rows}) != len(mapping_rows):
            raise DataError("Resolved provider mappings are not provider-number unique")
        pack_dir.mkdir(parents=True, exist_ok=True)
        for filename in ("providers.csv", "channels.csv", "channel_aliases.csv", "provider_channels.csv"):
            os.replace(staged / filename, pack_dir / filename)
    return {"subscriber_observed": len(observed), "channels": len(catalog.rows), "jiotv_mappings": sum(row["provider_id"] == "jiotv-plus" for row in mappings), "airtel_official_mappings": sum(row["provider_id"] == "airtel-digital-tv" for row in mappings), **metrics, **airtel_metrics}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the checked-in TV pack from source snapshots")
    parser.add_argument("--pack-dir", type=Path, default=ROOT / "data" / "tv" / "tv-channels")
    parser.add_argument("--sources", type=Path, default=ROOT / "sources" / "tv")
    args = parser.parse_args()
    print(generate(args.pack_dir, args.sources))


if __name__ == "__main__":
    try:
        main()
    except DataError as exc:
        raise SystemExit(f"TV import failed; existing production output was not replaced. {exc}") from exc
