# Production source data

Only verified source data belongs under this directory.

- Metro: `data/metro/<city>/`
- TV: `data/tv/<pack>/`

Create a correctly shaped source directory with `scripts/scaffold_pack.py`.

Do not copy the synthetic fixtures from `tests/fixtures/` into production. They exist only to test the builders.

Every production pack should include a maintained `COVERAGE.md` describing:

- what is included,
- what is intentionally excluded,
- last verification date,
- source URLs / source documents,
- licensing or reuse considerations,
- known gaps.

Before publishing third-party data, confirm that its terms allow the intended redistribution.
