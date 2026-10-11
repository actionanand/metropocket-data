# Metro pack schema

A Metro pack represents one versioned city network snapshot.

## Source files

- `pack.json`
- `stations.csv`
- `station_aliases.csv`
- `station_codes.csv`
- `lines.csv`
- `station_lines.csv`
- `connections.csv`
- `interchanges.csv`
- `COVERAGE.md`

`pack.json` supports:

```json
{
  "id": "metro-bengaluru",
  "type": "metro",
  "name": "Bengaluru Metro",
  "version": 1,
  "schemaVersion": 1,
  "city": "Bengaluru",
  "networkAsOf": "2026-10-01",
  "defaultEdgeMinutes": 3,
  "description": "Operational network snapshot.",
  "changes": []
}
```

Allowed operational status values:

- `operational`
- `under-construction`
- `planned`
- `temporarily-closed`

Only operational records should be used for ordinary client routing.

## Connections

Each source connection is one adjacent station pair on one line. `bidirectional` should normally be `1`.

Do not store every origin/destination route. The client calculates routes from adjacent graph edges.

`travel_minutes` may be blank when a verified segment time is unavailable. The client can fall back to `defaultEdgeMinutes` and label the result approximate.

## Lines and direction

Each line stores terminal station IDs. `station_lines.sequence` records line order. This is enough for a future client reader to derive boarding direction and validate line continuity.

## Network evolution

When a line is extended, append the new stations/edges and update status/version/networkAsOf. Future/under-construction records may already exist, but they must not be treated as operational until verified.
