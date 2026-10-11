PRAGMA foreign_keys = ON;

CREATE TABLE metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE stations (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('operational','under-construction','planned','temporarily-closed')),
  latitude REAL,
  longitude REAL
);

CREATE TABLE station_aliases (
  station_id TEXT NOT NULL,
  alias TEXT NOT NULL,
  PRIMARY KEY (station_id, alias),
  FOREIGN KEY (station_id) REFERENCES stations(id) ON DELETE CASCADE
);

CREATE TABLE station_codes (
  station_id TEXT NOT NULL,
  code TEXT NOT NULL,
  PRIMARY KEY (station_id, code),
  FOREIGN KEY (station_id) REFERENCES stations(id) ON DELETE CASCADE
);

CREATE TABLE lines (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  short_name TEXT,
  color TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('operational','under-construction','planned','temporarily-closed')),
  terminal_a_station_id TEXT,
  terminal_b_station_id TEXT,
  FOREIGN KEY (terminal_a_station_id) REFERENCES stations(id),
  FOREIGN KEY (terminal_b_station_id) REFERENCES stations(id)
);

CREATE TABLE station_lines (
  station_id TEXT NOT NULL,
  line_id TEXT NOT NULL,
  sequence INTEGER NOT NULL CHECK (sequence >= 0),
  PRIMARY KEY (station_id, line_id),
  UNIQUE (line_id, sequence),
  FOREIGN KEY (station_id) REFERENCES stations(id) ON DELETE CASCADE,
  FOREIGN KEY (line_id) REFERENCES lines(id) ON DELETE CASCADE
);

CREATE TABLE connections (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  from_station_id TEXT NOT NULL,
  to_station_id TEXT NOT NULL,
  line_id TEXT NOT NULL,
  travel_minutes REAL,
  status TEXT NOT NULL CHECK (status IN ('operational','under-construction','planned','temporarily-closed')),
  bidirectional INTEGER NOT NULL DEFAULT 1 CHECK (bidirectional IN (0,1)),
  FOREIGN KEY (from_station_id) REFERENCES stations(id),
  FOREIGN KEY (to_station_id) REFERENCES stations(id),
  FOREIGN KEY (line_id) REFERENCES lines(id)
);

CREATE TABLE interchanges (
  station_id TEXT NOT NULL,
  from_line_id TEXT NOT NULL,
  to_line_id TEXT NOT NULL,
  walk_minutes REAL,
  PRIMARY KEY (station_id, from_line_id, to_line_id),
  FOREIGN KEY (station_id) REFERENCES stations(id),
  FOREIGN KEY (from_line_id) REFERENCES lines(id),
  FOREIGN KEY (to_line_id) REFERENCES lines(id)
);

CREATE INDEX idx_station_aliases_alias ON station_aliases(alias COLLATE NOCASE);
CREATE INDEX idx_station_codes_code ON station_codes(code COLLATE NOCASE);
CREATE INDEX idx_station_lines_line_sequence ON station_lines(line_id, sequence);
CREATE INDEX idx_connections_from ON connections(from_station_id);
CREATE INDEX idx_connections_to ON connections(to_station_id);
CREATE INDEX idx_connections_line ON connections(line_id);
