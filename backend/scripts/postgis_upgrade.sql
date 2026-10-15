-- Optional: run on PostgreSQL+PostGIS after the API has created its tables.
-- Adds geography columns derived from lat/lon and GiST indexes for spatial queries.
CREATE EXTENSION IF NOT EXISTS postgis;
ALTER TABLE occurrences  ADD COLUMN IF NOT EXISTS geog geography(Point, 4326)
  GENERATED ALWAYS AS (CASE WHEN lat IS NOT NULL AND lon IS NOT NULL THEN ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography END) STORED;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS geog geography(Point, 4326)
  GENERATED ALWAYS AS (CASE WHEN lat IS NOT NULL AND lon IS NOT NULL THEN ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography END) STORED;
CREATE INDEX IF NOT EXISTS occurrences_geog_idx  ON occurrences  USING GIST (geog);
CREATE INDEX IF NOT EXISTS observations_geog_idx ON observations USING GIST (geog);
