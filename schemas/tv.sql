PRAGMA foreign_keys = ON;

CREATE TABLE metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE providers (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('dth','cable','iptv'))
);

CREATE TABLE channels (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  language TEXT,
  genre TEXT,
  quality TEXT CHECK (quality IS NULL OR quality IN ('SD','HD','4K'))
);

CREATE TABLE channel_aliases (
  channel_id TEXT NOT NULL,
  alias TEXT NOT NULL,
  PRIMARY KEY (channel_id, alias),
  FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
);

CREATE TABLE provider_channels (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider_id TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  number TEXT NOT NULL,
  country TEXT,
  state TEXT,
  city TEXT,
  area TEXT,
  revision TEXT,
  verified_at TEXT,
  source_url TEXT,
  FOREIGN KEY (provider_id) REFERENCES providers(id),
  FOREIGN KEY (channel_id) REFERENCES channels(id)
);

CREATE INDEX idx_channels_name ON channels(name COLLATE NOCASE);
CREATE INDEX idx_channels_language ON channels(language);
CREATE INDEX idx_channels_genre ON channels(genre);
CREATE INDEX idx_channels_quality ON channels(quality);
CREATE INDEX idx_channel_aliases_alias ON channel_aliases(alias COLLATE NOCASE);
CREATE INDEX idx_provider_channels_provider ON provider_channels(provider_id);
CREATE INDEX idx_provider_channels_channel ON provider_channels(channel_id);
CREATE INDEX idx_provider_channels_number ON provider_channels(number);
CREATE INDEX idx_provider_channels_region ON provider_channels(state, city, area);
CREATE INDEX idx_provider_channels_provider_number ON provider_channels(provider_id, number);
