from __future__ import annotations

import gzip
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
from scripts.common import DataError


class BuilderTests(unittest.TestCase):
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
                self.assertTrue(pack["downloadUrl"].startswith("https://github.com/actionanand/metropocket-data/releases/download/v-test/"))
                self.assertGreater(pack["downloadBytes"], 0)
                self.assertGreater(pack["installedBytes"], 0)
                self.assertEqual(len(pack["sha256"]), 64)

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
