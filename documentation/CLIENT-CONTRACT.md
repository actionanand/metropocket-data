# Client contract

This repository is aligned to the current MetroPocket client contract.

## Manifest

The browser/Capacitor client fetches:

```text
https://raw.githubusercontent.com/actionanand/metropocket-data/client-data/manifest.json
```

Top-level fields:

- `schemaVersion`: positive integer, currently exactly `1`
- `releaseVersion`: positive integer
- `generatedAt`: non-empty ISO-style string
- `packs`: array

Pack fields required by the client validator:

- `id`: non-empty string
- `type`: exactly `metro` or `tv`
- `name`: non-empty string
- `version`: positive integer
- `schemaVersion`: exactly `1`
- `file`: non-empty string
- `downloadUrl`: valid HTTPS URL under `raw.githubusercontent.com/actionanand/metropocket-data/client-data/<tag>/`

Optional fields supported by the client:

- `downloadBytes`: non-negative integer
- `installedBytes`: non-negative integer
- `sha256`: 64-character hexadecimal SHA-256 of the **downloaded `.db.gz` bytes**
- `city`
- `networkAsOf`
- `description`
- `changes`

The client currently verifies the compressed download checksum and stores the downloaded bytes. A later client data-reader layer will decompress/open the SQLite database.

## Important compatibility rule

Changing the SQLite table layout can be done without changing manifest `schemaVersion` only while the client does not depend on the changed table. Once a released client reads these databases, treat the DB contract as versioned and coordinate any breaking change with the client.
