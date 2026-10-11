# Data maintenance

## Metro update

1. Verify the official/current network.
2. Update CSV source rows.
3. Keep future stations with a non-operational status when useful.
4. Update `networkAsOf`.
5. Increment the pack `version`.
6. Update `COVERAGE.md`.
7. Run validation/tests/build.
8. Increment `releaseVersion` before the next published release.

## TV update

1. Verify the channel list against the provider/source.
2. Keep provider/channel IDs stable.
3. Update only the scoped mapping that changed.
4. Update `verified_at` and `source_url`.
5. Increment the TV pack `version`.
6. Update `COVERAGE.md`.
7. Run validation/tests/build.

Stable IDs are important. Renaming a display name should not require changing an existing ID.
