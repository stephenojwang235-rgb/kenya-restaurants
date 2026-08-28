-- Migration: Create restaurants table for Kenyan Restaurant Finder
-- Description: Stores restaurant data with geolocation and WhatsApp contact info
-- RLS: Public read-only access enabled

-- 1. Create the restaurants table
CREATE TABLE IF NOT EXISTS public.restaurants (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    county      TEXT NOT NULL,
    latitude    DOUBLE PRECISION NOT NULL,
    longitude   DOUBLE PRECISION NOT NULL,
    phone       TEXT,  -- International format, e.g. +254712345678
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. Add a check constraint to ensure latitude is valid (-90 to 90)
ALTER TABLE public.restaurants
    ADD CONSTRAINT restaurants_latitude_check
    CHECK (latitude >= -90 AND latitude <= 90);

-- 3. Add a check constraint to ensure longitude is valid (-180 to 180)
ALTER TABLE public.restaurants
    ADD CONSTRAINT restaurants_longitude_check
    CHECK (longitude >= -180 AND longitude <= 180);

-- 4. Add a check constraint to ensure phone starts with + (international format)
ALTER TABLE public.restaurants
    ADD CONSTRAINT restaurants_phone_format_check
    CHECK (phone IS NULL OR phone ~ '^\+[1-9][0-9]{6,14}$');

-- 5. Create an index on county for fast filtering by county
CREATE INDEX IF NOT EXISTS idx_restaurants_county
    ON public.restaurants (county);

-- 6. Create a spatial index (using btree on lat/lon for bounding box queries)
CREATE INDEX IF NOT EXISTS idx_restaurants_location
    ON public.restaurants (latitude, longitude);

-- 7. Create an index on name for search
CREATE INDEX IF NOT EXISTS idx_restaurants_name
    ON public.restaurants (name);

-- 8. Enable Row Level Security
ALTER TABLE public.restaurants ENABLE ROW LEVEL SECURITY;

-- 9. Create RLS policy: allow public read-only access to all rows
CREATE POLICY "Allow public read-only access"
    ON public.restaurants
    FOR SELECT
    USING (true);

-- 10. Revoke write privileges from anon and authenticated roles for defense-in-depth
REVOKE INSERT, UPDATE, DELETE ON public.restaurants FROM anon;
REVOKE INSERT, UPDATE, DELETE ON public.restaurants FROM authenticated;