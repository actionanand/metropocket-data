# Manifest and packaging

`build_all.py` creates `manifest.json` after every pack has been built.

`downloadBytes` is the compressed `.db.gz` byte size.

`installedBytes` is the uncompressed SQLite `.db` byte size.

`sha256` is calculated over the compressed `.db.gz` file because those are the exact bytes downloaded and verified by the MetroPocket client.

`downloadUrl` is generated as:

```text
https://github.com/<repository>/releases/download/<tag>/<filename>
```

The repository's stable latest release must contain `manifest.json`, because the client uses GitHub's `releases/latest/download/manifest.json` redirect.
