# Releases

The repository uses GitHub Releases as the public file host.

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
6. Run **Release data packs** from GitHub Actions with a new tag such as `v1`.
7. Confirm the release contains `manifest.json` and all expected `.db.gz` files.
8. Confirm the release is a normal stable release so GitHub's `/releases/latest/` redirect points to it.

Do not replace a published pack file under the same release/version. Publish a new pack version and a new release.
