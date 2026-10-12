# Releases

GitHub Releases are the canonical, versioned archive for MetroPocket data
packs. The `client-data` branch is a separate browser-runtime mirror: it
contains only `manifest.json` and versioned `.db.gz` assets and is served via
`raw.githubusercontent.com`, which is suitable for browser and Capacitor CORS
requests.

`client-data/manifest.json` is the latest browser manifest only.
`client-data/<tag>/*.db.gz` assets are immutable historical downloads, so an
older release remains verifiable after a newer browser manifest is published.
The GitHub Release manifest remains the canonical archive metadata.
The root manifest advances only to a higher `releaseVersion`; rerunning an old
release or the v1 bootstrap preserves a newer root. Existing tag assets must
have identical SHA-256 bytes or publication fails.

`bash scripts/publish_release.sh v1 --verify-only` verifies v1's Release
archive and immutable `client-data/v1/` pack URLs without requiring the root
manifest to still describe v1. Root-manifest equality is checked only for the
current latest release.

## Release steps

1. Update data sources.
2. Run:

```bash
python scripts/validate_sources.py
python -m unittest discover -s tests -v
```

3. Increment `releaseVersion` in `release.json`.
4. Increment each changed pack version.
5. Push the source changes.
6. Run `./scripts/publish_release.sh v2` from a clean `master` checkout.
7. Confirm the release contains `manifest.json` and all expected `.db.gz` files.
8. Confirm `https://raw.githubusercontent.com/actionanand/metropocket-data/client-data/manifest.json`
   contains the same manifest and its pack URLs point to the immutable tag directory.

Do not replace a published pack file under the same release/version. Publish a new pack version and a new release.

## TV-pack release boundary

The existing data release `v1` and its `client-data/v1/` mirror are immutable.
The initial combined Metro + TV publication must be data release `v2`; do not
add `tv-channels` to the historical v1 release or bootstrap it into the v1
client-data directory.

## Bootstrap the existing v1 release

This is needed only for the pre-mirror v1 release. It can be rerun safely and
does not change the GitHub Release:

```bash
bash scripts/bootstrap_client_data.sh v1 actionanand/metropocket-data
```

The bootstrap downloads and verifies the Release assets, rewrites only their
browser `downloadUrl` values for the client-data manifest, validates each pack,
and preserves any other tag directories already on `client-data`.
