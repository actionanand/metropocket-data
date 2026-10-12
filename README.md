# MetroPocket Data

`metropocket-data` is the data repository and release pipeline for the MetroPocket client.

Client repository: `https://github.com/actionanand/metro-pocket`

GitHub Releases are the canonical, versioned archive for CLI/manual downloads.
The MetroPocket browser/PWA and Capacitor runtime use the CORS-safe raw mirror
at:

`https://raw.githubusercontent.com/actionanand/metropocket-data/client-data/manifest.json`

This repository intentionally contains **no fabricated production station, route, travel-time, or TV channel-number data**. Production data is maintained as source CSV/JSON files, validated, converted into SQLite databases, compressed as deterministic `.db.gz` packs, and published as GitHub Release assets.

## What this repository produces

Typical release assets:

```text
manifest.json
metro-bengaluru.db.gz
metro-chennai.db.gz
metro-delhi-ncr.db.gz
tv-channels.db.gz
```

The manifest is generated from the built packs and includes the fields required by the client:

```json
{
  "schemaVersion": 1,
  "releaseVersion": 1,
  "generatedAt": "2026-10-12T00:00:00Z",
  "packs": [
    {
      "id": "metro-bengaluru",
      "type": "metro",
      "name": "Bengaluru Metro",
      "version": 1,
      "schemaVersion": 1,
      "file": "metro-bengaluru.db.gz",
      "downloadUrl": "https://raw.githubusercontent.com/actionanand/metropocket-data/client-data/v1/metro-bengaluru.db.gz",
      "downloadBytes": 12345,
      "installedBytes": 45678,
      "sha256": "...",
      "city": "Bengaluru",
      "networkAsOf": "2026-10-01"
    }
  ]
}
```

## Requirements

Only Python 3.11+ is required. The build/validation scripts use the Python standard library.

## First setup

Create a Metro source pack:

```bash
python scripts/scaffold_pack.py metro   --id metro-bengaluru   --name "Bengaluru Metro"   --city Bengaluru   --network-as-of 2026-10-01
```

Create the TV source pack:

```bash
python scripts/scaffold_pack.py tv   --id tv-channels   --name "India TV Channels"
```

Then populate the generated CSV files with verified source data.

## Validate

```bash
python scripts/validate_sources.py
python -m unittest discover -s tests -v
```

## Build locally

```bash
python scripts/build_all.py   --output dist   --repository actionanand/metropocket-data   --tag v1
```

The command builds all source packs found under `data/metro/*` and `data/tv/*`, creates `.db.gz` assets, and generates `dist/manifest.json`.

For an actual release, require at least one real pack:

```bash
python scripts/build_all.py   --output dist   --repository actionanand/metropocket-data   --tag v1   --require-packs
```

## Inspect a generated pack

```bash
python scripts/inspect_pack.py dist/metro-bengaluru.db.gz
```

## GitHub release

The included `Release data packs` workflow is manual. Run it from GitHub Actions and provide a new release tag such as `v1`.

Before every release:

1. Update source data and provenance.
2. Increment the changed pack's integer `version` in its `pack.json`.
3. Increment `releaseVersion` in `release.json`.
4. Update `networkAsOf` / verification dates.
5. Run validation and tests.
6. Publish the release workflow.

The release workflow uploads `manifest.json` and `.db.gz` files to the GitHub
Release, then mirrors only the `.db.gz` files under `client-data/<tag>/` and
updates `client-data/manifest.json`. Pack URLs in that manifest are immutable
and tag-specific.

## Repository layout

```text
config/                 Canonical city/provider identities
data/                   Real production source data
documentation/          Schemas, release and maintenance guidance
schemas/                SQLite schemas used by builders
scripts/                Build, validation, scaffold and inspection tools
templates/              Empty source-pack templates
tests/fixtures/          Synthetic test-only data
.github/workflows/       Validation and release automation
```

See `documentation/CLIENT-CONTRACT.md` first before changing any pack or manifest schema.
