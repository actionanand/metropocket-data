"""Fetch compact, reviewable TV-channel source snapshots.

This script deliberately stores parsed facts rather than page HTML.  It uses
only the standard library so it can run in a normal WSL Python environment.
"""
from __future__ import annotations

import argparse
import csv
import re
import time
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

try:
    from .common import ROOT, DataError
    from .import_tv_channels import resolve_airtel_official
except ImportError:
    from common import ROOT, DataError
    from import_tv_channels import resolve_airtel_official


SNAPSHOT_DATE = "2026-10-12"
AIRTEL_URL = "https://www.airtel.in/plans/dth/all-channel-list"
JIO_URL = "https://techiga.com/jiotv-plus-complete-live-tv-channel-list/"
USER_AGENT = "MetroPocketData/1.0 (+https://github.com/actionanand/metropocket-data)"
NUMBER_RE = re.compile(r"^\d+$")
RANGE_RE = re.compile(r"^\d+\s*-\s*\d+$")
AIRTEL_SCOPE_SLUGS = (
    "hindi", "english", "tamil", "telugu", "kannada", "malayalam", "bengali", "marathi",
    "gujarati", "punjabi", "odia", "bhojpuri", "assamese", "news", "sports", "movies", "music",
)


def clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def normalize_quality(value: str) -> str:
    labels = {label.upper() for label in re.findall(r"\b(?:SD|HD|4K)\b", value, flags=re.I)}
    if "4K" in labels:
        return "4K"
    if "HD" in labels:
        return "HD"
    if "SD" in labels:
        return "SD"
    return ""


def fetch_text(url: str, *, timeout: int = 30, retries: int = 3) -> str:
    """Fetch one URL with a small, polite retry budget."""
    last_error: Exception | None = None
    for attempt in range(retries):
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
        try:
            with urlopen(request, timeout=timeout) as response:  # nosec B310: fixed HTTPS source URLs
                status = getattr(response, "status", response.getcode())
                if status < 200 or status >= 300:
                    raise DataError(f"{url}: HTTP {status}")
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except HTTPError as exc:
            # A discovered but absent landing page is not a transient failure.
            if 400 <= exc.code < 500:
                raise DataError(f"{url}: HTTP {exc.code}") from exc
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
        except (URLError, TimeoutError, DataError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
    raise DataError(f"Could not fetch {url} after {retries} attempts: {last_error}")


class AirtelHTMLParser(HTMLParser):
    """Parse Airtel's accordion/card markup without depending on visual layout."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.languages: dict[str, str] = {}
        self._button_target = ""
        self._button_text: list[str] = []
        self._content_stack: list[str] = []
        self._card_depth = 0
        self._card_language = ""
        self._card_fields: list[str] = []
        self._paragraph_text: list[str] | None = None
        self.rows: list[dict[str, str]] = []

    @staticmethod
    def _has_class(attrs: dict[str, str], token: str) -> bool:
        return token in attrs.get("class", "").split()

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {key.lower(): value or "" for key, value in attrs_list}
        if tag == "button" and self._has_class(attrs, "accordion-toggle"):
            self._button_target = attrs.get("aria-controls", "")
            self._button_text = []
        if tag == "div":
            content_id = attrs.get("id", "")
            if content_id in self.languages:
                self._content_stack.append(content_id)
            elif self._content_stack:
                self._content_stack.append(self._content_stack[-1])
            if self._has_class(attrs, "pack-inner-item"):
                self._card_depth = 1
                active = self._content_stack[-1] if self._content_stack else ""
                self._card_language = self.languages.get(active, "")
                self._card_fields = []
                self._paragraph_text = None
            elif self._card_depth:
                self._card_depth += 1
        if tag == "p" and self._card_depth:
            self._paragraph_text = []

    def handle_data(self, data: str) -> None:
        if self._button_target:
            self._button_text.append(data)
        if self._paragraph_text is not None:
            self._paragraph_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "button" and self._button_target:
            language = clean("".join(self._button_text))
            if language:
                self.languages[self._button_target] = language
            self._button_target = ""
            self._button_text = []
        if tag == "p" and self._paragraph_text is not None:
            value = clean("".join(self._paragraph_text))
            if value:
                self._card_fields.append(value)
            self._paragraph_text = None
        if tag == "div" and self._card_depth:
            self._card_depth -= 1
            if not self._card_depth:
                # Airtel cards conventionally expose quality, number, name, genre, price.
                fields = self._card_fields
                number_index = next((i for i, value in enumerate(fields) if NUMBER_RE.fullmatch(value)), None)
                if number_index is not None and number_index + 1 < len(fields):
                    self.rows.append({
                        "number": fields[number_index],
                        "name": fields[number_index + 1],
                        "language": self._card_language,
                        "genre": fields[number_index + 2] if number_index + 2 < len(fields) else "",
                        "quality": normalize_quality(" ".join(fields[:number_index + 1])),
                    })
        elif tag == "div" and self._content_stack:
            self._content_stack.pop()


def parse_airtel_html(html: str) -> list[dict[str, str]]:
    parser = AirtelHTMLParser()
    parser.feed(html)
    parser.close()
    rows = []
    seen: set[tuple[str, ...]] = set()
    for row in parser.rows:
        normalized = {key: clean(value) for key, value in row.items()}
        if not NUMBER_RE.fullmatch(normalized["number"]) or not normalized["name"]:
            continue
        key = tuple(normalized[field] for field in ("number", "name", "language", "genre", "quality"))
        if key not in seen:
            seen.add(key)
            rows.append(normalized)
    return sorted(rows, key=lambda row: (row["language"].casefold(), int(row["number"]), row["name"].casefold()))


class AirtelLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: set[str] = set()

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs_list).get("href") or ""
        if "/plans/dth/" in href and "channel" in href:
            self.links.add(href)


def scope_from_url(url: str) -> str:
    slug = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1].removesuffix("-channels")
    genre = {"news", "sports", "movies", "music"}
    return f"genre:{slug.title()}" if slug in genre else f"language:{slug.title()}"


def discover_airtel_pages(aggregate_html: str) -> list[str]:
    """Discover official scoped catalogues, then safely probe conventional links.

    Every candidate is accepted only when it returns valid Airtel card data.
    The fallback permits discovery when the aggregate navigation is client-side.
    """
    parser = AirtelLinkParser()
    parser.feed(aggregate_html)
    parser.close()
    candidates = {urljoin(AIRTEL_URL, href).split("?", 1)[0] for href in parser.links}
    candidates.update(urljoin(AIRTEL_URL, f"/plans/dth/{slug}-channels") for slug in AIRTEL_SCOPE_SLUGS)
    candidates.discard(AIRTEL_URL)
    return sorted(url for url in candidates if urlparse(url).netloc == urlparse(AIRTEL_URL).netloc)


def fetch_airtel_rows() -> list[dict[str, str]]:
    aggregate_html = fetch_text(AIRTEL_URL)
    aggregate = [{**row, "source_url": AIRTEL_URL, "source_scope": "aggregate"} for row in parse_airtel_html(aggregate_html)]
    supplementary: list[dict[str, str]] = []
    for url in discover_airtel_pages(aggregate_html):
        try:
            scoped = parse_airtel_html(fetch_text(url))
        except DataError:
            continue
        if scoped:
            supplementary.extend({**row, "source_url": url, "source_scope": scope_from_url(url)} for row in scoped)
    # Preserve distinct provenance rows; the importer resolves their facts.
    return sorted(aggregate + supplementary, key=lambda row: (row["source_scope"], int(row["number"]), row["name"].casefold(), row["source_url"]))


def language_from_heading(heading: str) -> str:
    heading = clean(heading)
    match = re.search(r"jiotv\+?\s+(.+?)\s+channel\s+list", heading, re.I)
    value = clean(match.group(1) if match else heading)
    if re.search(r"\b(?:and|&|other)\b", value, re.I):
        return ""
    known = {"assamese", "bengali", "bhojpuri", "english", "gujarati", "hindi", "kannada", "malayalam", "marathi", "odia", "oriya", "punjabi", "tamil", "telugu", "urdu"}
    return value.title() if value.casefold() in known else ""


class JioHTMLParser(HTMLParser):
    """Extract table and list facts grouped by nearby semantic headings."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.heading_level = 0
        self.heading_text: list[str] = []
        self.language = ""
        self.in_row = False
        self.cells: list[str] = []
        self.cell_text: list[str] | None = None
        self.block_tag = ""
        self.block_text: list[str] = []
        self.rows: list[tuple[str, str, str]] = []
        self.blocks: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.heading_level = 1
            self.heading_text = []
        elif tag == "tr":
            self.in_row = True
            self.cells = []
        elif tag in {"td", "th"} and self.in_row:
            self.cell_text = []
        elif tag in {"p", "li"} and not self.in_row:
            self.block_tag = tag
            self.block_text = []
        elif tag == "br" and self.block_tag:
            self.block_text.append("\n")

    def handle_data(self, data: str) -> None:
        if self.heading_level:
            self.heading_text.append(data)
        if self.cell_text is not None:
            self.cell_text.append(data)
        elif self.block_tag:
            self.block_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self.heading_level:
            self.language = language_from_heading("".join(self.heading_text))
            self.heading_level = 0
        elif tag in {"td", "th"} and self.cell_text is not None:
            self.cells.append(clean("".join(self.cell_text)))
            self.cell_text = None
        elif tag == "tr" and self.in_row:
            for index in range(0, len(self.cells) - 1, 2):
                self.rows.append((self.cells[index], self.cells[index + 1], self.language))
            self.in_row = False
        elif tag == self.block_tag and self.block_tag:
            block = "".join(self.block_text).strip()
            if block:
                self.blocks.append((block, self.language))
            self.block_tag = ""
            self.block_text = []


def parse_jio_html(html: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    parser = JioHTMLParser()
    parser.feed(html)
    parser.close()
    candidates = list(parser.rows)
    # WordPress posts often use plain numbered lines instead of a real table.
    line_pattern = re.compile(r"(?m)^\s*(\d+(?:\s*-\s*\d+)?)\s*[.)]\s*(.+?)\s*$")
    for block, language in parser.blocks:
        for number, name in line_pattern.findall(block):
            candidates.append((name, number, language))
    rows: list[dict[str, str]] = []
    ranges: list[dict[str, str]] = []
    for name, number, language in candidates:
        name, number, language = clean(name), clean(number), clean(language)
        if RANGE_RE.fullmatch(number):
            ranges.append({"number": number, "name": name, "language": language, "reason": "range without individual identities"})
        elif NUMBER_RE.fullmatch(number) and name and name.casefold() not in {"channel name", "name"}:
            rows.append({"number": number, "name": name, "language": language, "genre": "", "quality": normalize_quality(name)})
    # Exact duplicate source facts carry no additional information; conflicting rows stay.
    unique = {tuple(row[field] for field in ("number", "name", "language", "genre", "quality")): row for row in rows}
    return (
        sorted(unique.values(), key=lambda row: (int(row["number"]), row["name"].casefold(), row["language"].casefold())),
        sorted(ranges, key=lambda row: (row["number"], row["name"].casefold())),
    )


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return [{key: clean(value or "") for key, value in row.items() if key is not None} for row in csv.DictReader(handle)]


def conflict_rows(external: list[dict[str, str]], subscriber: list[dict[str, str]], ranges: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in external:
        grouped[row["number"]].add(row["name"])
    subscriber_by_number = {row["number"]: row["name"] for row in subscriber}
    rows = []
    for number, names in grouped.items():
        observed = subscriber_by_number.get(number, "")
        if observed:
            rows.append({"number": number, "external_names": " | ".join(sorted(names)), "subscriber_name": observed,
                         "resolution": "subscriber override",
                         "reason": "subscriber-observed mapping takes precedence"})
        elif len(names) > 1:
            rows.append({"number": number, "external_names": " | ".join(sorted(names)), "subscriber_name": observed,
                         "resolution": "excluded",
                         "reason": "conflicting external names for one provider number"})
    for row in ranges:
        rows.append({"number": row["number"], "external_names": row["name"], "subscriber_name": "",
                     "resolution": "excluded", "reason": row["reason"]})
    return sorted(rows, key=lambda row: (int(row["number"].split("-")[0].strip()), row["number"], row["external_names"].casefold()))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and compact Airtel and JioTV+ source snapshots")
    parser.add_argument("--sources", type=Path, default=ROOT / "sources" / "tv")
    parser.add_argument("--date", default=SNAPSHOT_DATE, help="dated snapshot label (default: %(default)s)")
    parser.add_argument("--airtel-only", action="store_true", help="refresh Airtel aggregate and dedicated official evidence only")
    args = parser.parse_args()
    airtel = fetch_airtel_rows()
    if not airtel:
        raise DataError("Airtel response contained no structured numeric channel cards; review the page markup before replacing the snapshot")
    airtel_rows = [{**row, "verified_at": args.date} for row in airtel]
    write_csv(args.sources / "airtel-digital-tv" / f"official-{args.date}.csv",
              ["number", "name", "language", "genre", "quality", "source_url", "source_scope", "verified_at"], airtel_rows)
    _, airtel_conflicts, airtel_metrics = resolve_airtel_official(airtel_rows)
    write_csv(args.sources / "airtel-digital-tv" / f"conflicts-{args.date}.csv",
              ["number", "aggregate_names", "dedicated_names", "chosen_name", "chosen_source_url", "resolution", "reason"], airtel_conflicts)
    print(f"Airtel source rows: {len(airtel_rows)}")
    print(f"Airtel dedicated rows: {sum(row['source_scope'] != 'aggregate' for row in airtel_rows)}")
    print(f"Airtel aggregate conflicts resolved: {airtel_metrics['airtel_aggregate_conflicts_resolved']}")
    print(f"Airtel conflicts excluded: {airtel_metrics['airtel_conflicts_excluded']}")
    if args.airtel_only:
        return
    jio, ranges = parse_jio_html(fetch_text(JIO_URL))
    if not jio:
        raise DataError("Jio source contained no numeric channel rows; review the page markup before replacing the snapshot")
    jio_rows = [{**row, "source_url": JIO_URL, "retrieved_at": args.date} for row in jio]
    write_csv(args.sources / "jiotv-plus" / f"external-{args.date}.csv",
              ["number", "name", "language", "genre", "quality", "source_url", "retrieved_at"], jio_rows)
    observed = read_csv_rows(args.sources / "jiotv-plus" / f"user-observed-{args.date}.csv")
    conflicts = conflict_rows(jio, observed, ranges)
    write_csv(args.sources / "jiotv-plus" / f"conflicts-{args.date}.csv",
              ["number", "external_names", "subscriber_name", "resolution", "reason"], conflicts)
    print(f"Jio external source rows: {len(jio_rows)}")
    print(f"Jio unresolved ranges: {len(ranges)}")
    print(f"Jio source conflicts: {len(conflicts)}")
    print(f"Jio subscriber rows: {len(observed)}")


if __name__ == "__main__":
    main()
