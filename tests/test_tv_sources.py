from __future__ import annotations

import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.fetch_tv_sources import conflict_rows, parse_airtel_html, parse_jio_html
from scripts.common import DataError
from scripts.import_tv_channels import apply_airtel_scope_metadata, generate, normalize_genre, normalize_language, read_rows, resolve_airtel_official


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "tv-sources"


class TVSourceTests(unittest.TestCase):
    def test_filter_normalizers_remove_known_heading_artifacts_and_use_controlled_genres(self):
        self.assertEqual(normalize_language("Assamese +"), "Assamese")
        self.assertEqual(normalize_language(" Gujarati + "), "Gujarati")
        self.assertEqual(normalize_language("Urdu +"), "Urdu")
        self.assertEqual(normalize_language("Tamil+Cinema"), "Tamil+Cinema")
        self.assertEqual(normalize_genre("GEC"), "Entertainment")
        self.assertEqual(normalize_genre("General Entertainment Channel"), "Entertainment")
        self.assertEqual(normalize_genre("English"), "")
        self.assertEqual(normalize_genre("Business News"), "Business")
        self.assertEqual(normalize_genre("FTA"), "Other")
        self.assertEqual(apply_airtel_scope_metadata([{"language": "", "source_scope": "language:Punjabi"}])[0]["language"], "Punjabi")
        self.assertEqual(apply_airtel_scope_metadata([{"language": "", "source_scope": "genre:News"}])[0]["language"], "")

    def test_airtel_dedicated_pages_resolve_563_564_and_exclude_only_unresolved_numbers(self):
        rows = read_rows(FIXTURES / "airtel-conflicts.csv")
        retained, report, metrics = resolve_airtel_official(rows)
        self.assertEqual({(row["number"], row["name"]) for row in retained if row["number"] in {"563", "564"}}, {("563", "PTC NEWS"), ("564", "ABP Sanjha")})
        self.assertIn(("700", "Duplicate TV"), {(row["number"], row["name"]) for row in retained})
        self.assertNotIn("701", {row["number"] for row in retained})
        self.assertNotIn("702", {row["number"] for row in retained})
        self.assertEqual(metrics["airtel_aggregate_conflicts_resolved"], 1)
        self.assertEqual(metrics["airtel_conflicts_excluded"], 2)
        self.assertEqual(metrics["airtel_duplicate_rows_collapsed"], 2)
        self.assertEqual(next(row for row in report if row["number"] == "563")["chosen_name"], "PTC NEWS")

    def test_airtel_cards_keep_language_and_explicit_quality(self):
        rows = parse_airtel_html((FIXTURES / "airtel-sample.html").read_text(encoding="utf-8"))
        self.assertEqual(rows, [
            {"number": "202", "name": "Sample World", "language": "English", "genre": "Infotainment", "quality": "4K"},
            {"number": "101", "name": "Sample Tamil News", "language": "Tamil", "genre": "News", "quality": "HD"},
        ])

    def test_jio_parser_rejects_ranges_and_retains_heading_language_only_when_clear(self):
        rows, ranges = parse_jio_html((FIXTURES / "jio-sample.html").read_text(encoding="utf-8"))
        self.assertIn({"number": "301", "name": "Kannada One HD", "language": "Kannada", "genre": "", "quality": "HD"}, rows)
        self.assertIn({"number": "401", "name": "Mixed Service", "language": "", "genre": "", "quality": ""}, rows)
        self.assertEqual(ranges[0]["number"], "372-380")

    def test_jio_conflict_report_marks_subscriber_override_and_range(self):
        rows, ranges = parse_jio_html((FIXTURES / "jio-sample.html").read_text(encoding="utf-8"))
        report = conflict_rows(rows, [{"number": "1559", "name": "Sun News"}], ranges)
        override = next(row for row in report if row["number"] == "1559")
        self.assertEqual(override["resolution"], "subscriber override")
        self.assertEqual(next(row for row in report if row["number"] == "372-380")["resolution"], "excluded")

    def test_importer_gives_subscriber_mapping_precedence_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sources = root / "sources"
            shutil.copytree(ROOT / "sources" / "tv" / "jiotv-plus", sources / "jiotv-plus")
            (sources / "airtel-digital-tv").mkdir()
            rows, _ = parse_jio_html((FIXTURES / "jio-sample.html").read_text(encoding="utf-8"))
            with (sources / "jiotv-plus" / "external-2026-10-12.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["number", "name", "language", "genre", "quality", "source_url", "retrieved_at"])
                writer.writeheader()
                writer.writerows([{**row, "source_url": "https://example.test", "retrieved_at": "2026-10-12"} for row in rows])
            with (sources / "airtel-digital-tv" / "official-2026-10-12.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["number", "name", "language", "genre", "quality", "source_url", "verified_at"])
                writer.writeheader()
                writer.writerow({"number": "101", "name": "Airtel Test", "language": "Tamil", "genre": "News", "quality": "SD", "source_url": "https://example.test", "verified_at": "2026-10-12"})
            first, second = root / "one", root / "two"
            result = generate(first, sources)
            generate(second, sources)
            self.assertEqual(result["subscriber_observed"], 72)
            self.assertEqual(result["jio_conflicts_overridden"], 1)
            self.assertEqual((first / "provider_channels.csv").read_bytes(), (second / "provider_channels.csv").read_bytes())
            mappings = (first / "provider_channels.csv").read_text(encoding="utf-8")
            self.assertIn("jiotv-plus,sun-news,1559,IN,,,,subscriber-observed-2026-10-12", mappings)
            self.assertNotIn("wrong-external-name,1559", mappings)

    def test_importer_allows_provider_scoped_number_reuse_and_does_not_replace_on_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sources = root / "sources"
            shutil.copytree(ROOT / "sources" / "tv" / "jiotv-plus", sources / "jiotv-plus")
            shutil.copytree(ROOT / "sources" / "tv" / "airtel-digital-tv", sources / "airtel-digital-tv")
            # A provider-scoped number may legitimately overlap the Jio subscriber number.
            with (sources / "airtel-digital-tv" / "official-2026-10-12.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["number", "name", "language", "genre", "quality", "source_url", "source_scope", "verified_at"])
                writer.writeheader()
                writer.writerow({"number": "1559", "name": "Airtel Same Number", "language": "English", "genre": "News", "quality": "SD", "source_url": "https://example.test", "source_scope": "aggregate", "verified_at": "2026-10-12"})
            pack = root / "pack"
            result = generate(pack, sources)
            self.assertEqual(result["airtel_official_mappings"], 1)
            mappings = (pack / "provider_channels.csv").read_text(encoding="utf-8")
            self.assertIn("jiotv-plus,sun-news,1559", mappings)
            self.assertIn("airtel-digital-tv,airtel-same-number,1559", mappings)
            before = (pack / "provider_channels.csv").read_bytes()
            observed = sources / "jiotv-plus" / "user-observed-2026-10-12.csv"
            observed.write_text("number,name,native_name,language,genre\n", encoding="utf-8")
            with self.assertRaises(DataError):
                generate(pack, sources)
            self.assertEqual((pack / "provider_channels.csv").read_bytes(), before)

    def test_current_production_filter_domains_and_subscriber_examples(self):
        with tempfile.TemporaryDirectory() as temp:
            pack = Path(temp) / "pack"
            result = generate(pack, ROOT / "sources" / "tv")
            channels = read_rows(pack / "channels.csv", ("id", "language", "genre"))
            mappings = read_rows(pack / "provider_channels.csv", ("provider_id", "channel_id", "number"))
            aliases = read_rows(pack / "channel_aliases.csv", ("channel_id", "alias"))
            allowed_genres = {"", "Entertainment", "Movies", "News", "Sports", "Music", "Kids", "Devotional", "Infotainment", "Lifestyle", "Education", "Business", "Shopping", "International", "Regional", "Other"}
            self.assertTrue(all(not row["language"].endswith(" +") for row in channels))
            self.assertTrue(all(row["genre"] in allowed_genres for row in channels))
            self.assertNotIn("English", {row["genre"] for row in channels})
            self.assertNotIn("Gec", {row["genre"] for row in channels})
            self.assertEqual(result["subscriber_observed"], 72)
            channel_ids = {(row["provider_id"], row["number"]): row["channel_id"] for row in mappings}
            self.assertEqual(channel_ids[("jiotv-plus", "1559")], "sun-news")
            self.assertEqual(channel_ids[("jiotv-plus", "1503")], "sun-tv")
            self.assertEqual(channel_ids[("jiotv-plus", "1540")], "ktv")
            self.assertEqual(channel_ids[("jiotv-plus", "1579")], "sun-music")
            self.assertEqual(channel_ids[("jiotv-plus", "693")], "chutti-tv")
            self.assertIn({"channel_id": "sun-news", "alias": "சன் நியூஸ்"}, aliases)


if __name__ == "__main__":
    unittest.main()
