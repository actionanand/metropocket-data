# Bengaluru Metro Coverage

- Last verified: 2026-10-12

## Included operational lines

- Purple Line: Whitefield (Kadugodi) to Challaghatta
- Green Line: Madavara to Silk Institute
- Yellow Line: Rashtreeya Vidyalaya Road (RV Road) to Delta Electronics Bommasandra

## Included operational data

- 83 unique operational stations
- 37 Purple Line station memberships
- 32 Green Line station memberships
- 16 Yellow Line station memberships
- Adjacent station connections for all three operational lines
- Purple/Green interchange at Nadaprabhu Kempegowda Station (Majestic)
- Green/Yellow interchange at RV Road
- Common passenger-facing station aliases

## Future / under-construction network

Future and under-construction corridors are intentionally not included in normal routing in this version.

## Known exclusions

- Exact station latitude/longitude is not populated yet
- Official station codes are not populated yet
- Exact station-to-station travel times are not populated yet
- Exact interchange walking times are not populated yet
- Live train timings, departures, disruptions and service status are not provided

## Timing methodology

`connections.csv` leaves `travel_minutes` blank where an authoritative segment time is unavailable.

The pack currently uses:

- `defaultEdgeMinutes`: 3
- unspecified interchange walking time: handled by the MetroPocket client fallback

Travel duration shown by the client must therefore be treated as approximate.

## Sources

Primary verification source:

- Bangalore Metro Rail Corporation Limited (BMRCL)
- BMRCL About Us / operational network information
- BMRCL Metro Network information
- BMRCL station/parking listings

Station aliases are passenger-friendly search terms and are not intended to represent separate official station names.

## Redistribution / licensing notes

This repository stores structured factual transit data rather than reproducing BMRCL artwork, maps or branding assets.

Source provenance and verification dates should be retained whenever this pack is updated.
