# TV pack schema

The TV pack is region-aware because cable LCNs can vary by state, city, area or head-end.

## Source files

- `pack.json`
- `providers.csv`
- `channels.csv`
- `channel_aliases.csv`
- `provider_channels.csv`
- `COVERAGE.md`

## Providers

Provider `kind` must be `dth`, `cable`, or `iptv`. JioTV+ is modelled as
`iptv`; clients must add support for that provider kind before this pack is
released to them.

Canonical provider identities are listed in `config/tv-providers.json`.

## Channels

A channel is normalized once and can have aliases. Supported quality values are `SD`, `HD`, `4K`, or blank.

## Provider mappings

`provider_channels.csv` fields:

- `provider_id`
- `channel_id`
- `number`
- `country`
- `state`
- `city`
- `area`
- `revision`
- `verified_at`
- `source_url`

Leave a region field blank only when that mapping really applies at the broader scope.

Do not assume a cable provider uses one channel number nationwide.

If a mapping is unavailable or unverified, omit it. The client should show “Not available in installed data” rather than using a guess.
