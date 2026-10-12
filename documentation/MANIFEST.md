# Manifest and packaging

`build_all.py` creates `manifest.json` after every pack has been built.

`downloadBytes` is the compressed `.db.gz` byte size.

`installedBytes` is the uncompressed SQLite `.db` byte size.

`sha256` is calculated over the compressed `.db.gz` file because those are the exact bytes downloaded and verified by the MetroPocket client.

`downloadUrl` is generated as an immutable browser endpoint:

```text
https://raw.githubusercontent.com/<repository>/client-data/<tag>/<filename>
```

The same manifest is uploaded to the GitHub Release archive and published as
`client-data/manifest.json`. GitHub Release assets remain the canonical
versioned archive; the `client-data` copy exists solely for browser/Capacitor
runtime downloads.

The root `client-data/manifest.json` always describes the newest browser
release. Historical pack downloads remain available at their tag-specific URLs
even after this root manifest advances.

Publishing an older tag never moves the root backward. A collision with a
different byte sequence in an already-published `client-data/<tag>/` file is a
failure, not an overwrite.
