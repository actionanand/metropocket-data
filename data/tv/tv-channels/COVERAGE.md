# Coverage

- Snapshot date label: 2026-10-12. This is an offline channel-number
  catalogue, not a live programme guide; provider line-ups can change.
- Providers: JioTV+ (`iptv`) and Airtel Digital TV (`dth`).
- Airtel source: the official catalogue at
  https://www.airtel.in/plans/dth/all-channel-list. Run
  `python scripts/fetch_tv_sources.py` to create its dated compact snapshot.
  The snapshot retains `aggregate` versus dedicated language/category source
  scope; unambiguous dedicated official evidence takes precedence when the
  aggregate catalogue conflicts.
- JioTV+ sources: the authoritative 72 subscriber-observed mappings in
  `sources/tv/jiotv-plus/user-observed-2026-10-12.csv`, followed by the
  secondary Techiga catalogue snapshot. Subscriber observations have the
  highest precedence for an identical JioTV+ number.
- Jio official product page: https://www.jio.com/jiohome/services/jiotvplus/
- Jio third-party cross-check source (never higher priority than observations):
  https://techiga.com/jiotv-plus-complete-live-tv-channel-list/
- Languages currently represented in the subscriber snapshot: Tamil; language
  is intentionally blank for factual/international services whose primary
  audio language cannot be established from the subscriber UI alone.
- Genres currently represented: News, Devotional, Infotainment, Lifestyle,
  Entertainment, Movies, Music, Kids, Other.
- Quality is blank unless a source explicitly identifies it.
- The fetcher records only numeric source rows. Jio ranges without explicitly
  identified channels and external same-number conflicts are excluded from
  production mappings and reported in `sources/tv/jiotv-plus/conflicts-*.csv`.
- This document makes no static claim about fetched row counts. Use
  `python scripts/report_tv_pack.py` after fetching and importing for the
  generated coverage counts.
