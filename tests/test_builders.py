from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_all import build_all
from scripts.build_metro import build_pack as build_metro, validate_source as validate_metro
from scripts.build_tv import build_pack as build_tv, validate_source as validate_tv
from scripts.client_mirror import (
    browser_manifest_for_tag,
    publish_mirror,
    root_manifest_action,
    root_manifest_applies_to_tag,
)
from scripts.common import DataError
from scripts.import_tv_channels import generate as generate_tv_channels


class BuilderTests(unittest.TestCase):
    def test_jio_subscriber_snapshot_generates_exactly_72_mappings(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp)
            result = generate_tv_channels(pack, ROOT / "sources" / "tv")
            self.assertEqual(result["subscriber_observed"], 72)
            self.assertGreaterEqual(result["jiotv_mappings"], 72)
            self.assertIn("jiotv-plus,JioTV+,iptv", (pack / "providers.csv").read_text(encoding="utf-8"))
            mappings = (pack / "provider_channels.csv").read_text(encoding="utf-8")
            aliases = (pack / "channel_aliases.csv").read_text(encoding="utf-8")
            self.assertIn("jiotv-plus,sun-news,1559,IN,,,,subscriber-observed-2026-10-12,2026-10-12,", mappings)
            self.assertIn("sun-news,சன் நியூஸ்", aliases)

    def test_metro_fixture_builds_valid_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            descriptor = build_metro(
                ROOT / "tests" / "fixtures" / "metro-demo",
                out,
                "actionanand/metropocket-data",
                "v-test",
            )
            self.assertEqual(descriptor["type"], "metro")
            self.assertEqual(len(descriptor["sha256"]), 64)
            gz = out / descriptor["file"]
            with gzip.open(gz, "rb") as src, tempfile.NamedTemporaryFile(suffix=".db") as db_file:
                db_file.write(src.read())
                db_file.flush()
                connection = sqlite3.connect(db_file.name)
                try:
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM stations").fetchone()[0], 4)
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM connections").fetchone()[0], 3)
                    self.assertEqual(dict(connection.execute("SELECT key,value FROM metadata"))["city"], "Demo City")
                finally:
                    connection.close()

    def test_tv_fixture_builds_valid_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            descriptor = build_tv(
                ROOT / "tests" / "fixtures" / "tv-demo",
                out,
                "actionanand/metropocket-data",
                "v-test",
            )
            self.assertEqual(descriptor["type"], "tv")
            gz = out / descriptor["file"]
            with gzip.open(gz, "rb") as src, tempfile.NamedTemporaryFile(suffix=".db") as db_file:
                db_file.write(src.read())
                db_file.flush()
                connection = sqlite3.connect(db_file.name)
                try:
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM providers").fetchone()[0], 2)
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM provider_channels").fetchone()[0], 2)
                finally:
                    connection.close()

    def test_build_all_manifest_matches_client_contract(self):
        with tempfile.TemporaryDirectory() as source_tmp, tempfile.TemporaryDirectory() as out_tmp:
            source = Path(source_tmp)
            (source / "metro").mkdir(parents=True)
            (source / "tv").mkdir(parents=True)
            import shutil
            shutil.copytree(ROOT / "tests" / "fixtures" / "metro-demo", source / "metro" / "demo")
            shutil.copytree(ROOT / "tests" / "fixtures" / "tv-demo", source / "tv" / "demo")
            manifest = build_all(
                source,
                Path(out_tmp),
                "actionanand/metropocket-data",
                "v-test",
                release_version=7,
                require_packs=True,
            )
            self.assertEqual(manifest["schemaVersion"], 1)
            self.assertEqual(manifest["releaseVersion"], 7)
            self.assertEqual({p["type"] for p in manifest["packs"]}, {"metro", "tv"})
            for pack in manifest["packs"]:
                self.assertEqual(
                    pack["downloadUrl"],
                    f"https://raw.githubusercontent.com/actionanand/metropocket-data/client-data/v-test/{pack['file']}",
                )
                self.assertGreater(pack["downloadBytes"], 0)
                self.assertGreater(pack["installedBytes"], 0)
                self.assertEqual(len(pack["sha256"]), 64)

    def test_browser_manifest_rewrites_only_legacy_v1_release_urls(self):
        release = {
            "releaseVersion": 1,
            "packs": [{
                "file": "metro-bengaluru.db.gz",
                "downloadUrl": "https://github.com/actionanand/metropocket-data/releases/download/v1/metro-bengaluru.db.gz",
            }],
        }
        browser = browser_manifest_for_tag(
            release, "actionanand/metropocket-data", "v1", allow_legacy_v1_urls=True
        )
        self.assertEqual(
            browser["packs"][0]["downloadUrl"],
            "https://raw.githubusercontent.com/actionanand/metropocket-data/client-data/v1/metro-bengaluru.db.gz",
        )
        self.assertNotEqual(browser, release)
        with self.assertRaises(DataError):
            browser_manifest_for_tag(release, "actionanand/metropocket-data", "v2")

    def test_root_manifest_only_applies_to_its_latest_release_tag(self):
        root = {"releaseVersion": 2}
        self.assertTrue(root_manifest_applies_to_tag(root, "v2"))
        self.assertFalse(root_manifest_applies_to_tag(root, "v1"))

    def test_root_manifest_is_monotonic_and_rejects_same_version_conflicts(self):
        v1 = {"releaseVersion": 1, "packs": []}
        v2 = {"releaseVersion": 2, "packs": []}
        self.assertEqual(root_manifest_action(None, v1), "create")
        self.assertEqual(root_manifest_action(v1, v1), "unchanged")
        self.assertEqual(root_manifest_action(v1, v2), "update")
        self.assertEqual(root_manifest_action(v2, v1), "preserve-newer")
        with self.assertRaises(DataError):
            root_manifest_action(v1, {"releaseVersion": 1, "packs": [{"id": "conflict"}]})

    def test_publish_mirror_preserves_root_and_rejects_asset_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            assets = base / "assets"
            worktree = base / "worktree"
            assets.mkdir()
            worktree.mkdir()
            filename = "metro-bengaluru.db.gz"
            asset = assets / filename
            asset.write_bytes(b"first bytes")
            digest = hashlib.sha256(asset.read_bytes()).hexdigest()
            manifest = {
                "releaseVersion": 1,
                "packs": [{"file": filename, "sha256": digest,
                           "downloadUrl": "https://raw.githubusercontent.com/actionanand/metropocket-data/client-data/v1/metro-bengaluru.db.gz"}],
            }
            _, action, copied = publish_mirror(worktree, assets, manifest, "actionanand/metropocket-data", "v1")
            self.assertEqual((action, copied), ("create", [filename]))
            _, action, copied = publish_mirror(worktree, assets, manifest, "actionanand/metropocket-data", "v1")
            self.assertEqual((action, copied), ("unchanged", []))
            (worktree / "manifest.json").write_text('{"releaseVersion": 2, "packs": []}', encoding="utf-8")
            _, action, _ = publish_mirror(worktree, assets, manifest, "actionanand/metropocket-data", "v1")
            self.assertEqual(action, "preserve-newer")
            (worktree / "v1" / filename).write_bytes(b"different bytes")
            with self.assertRaises(DataError):
                publish_mirror(worktree, assets, manifest, "actionanand/metropocket-data", "v1")

    def test_invalid_metro_reference_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            import shutil
            folder = Path(tmp) / "metro"
            shutil.copytree(ROOT / "tests" / "fixtures" / "metro-demo", folder)
            path = folder / "connections.csv"
            text = path.read_text(encoding="utf-8").replace("a,b,green", "missing,b,green")
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(DataError):
                validate_metro(folder)

    def test_unknown_tv_provider_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            import shutil
            folder = Path(tmp) / "tv"
            shutil.copytree(ROOT / "tests" / "fixtures" / "tv-demo", folder)
            path = folder / "providers.csv"
            text = path.read_text(encoding="utf-8").replace("tata-play,Tata Play,dth", "unknown,Unknown,dth")
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(DataError):
                validate_tv(folder)


if __name__ == "__main__":
    unittest.main()
