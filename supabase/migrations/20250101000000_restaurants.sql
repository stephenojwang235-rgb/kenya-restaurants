-- ============================================================================
-- Kenyan Restaurant Finder — Restaurants table
-- Supabase + PostgreSQL
-- ============================================================================

-- Enable UUID generation extension (included in Supabase by default)
create extension if not exists "uuid-ossp";

-- ---------------------------------------------------------------------------
-- restaurants
-- ---------------------------------------------------------------------------
-- Stores each restaurant discovered in Kenya. Latitude / longitude are
-- deliberately stored as plain numeric columns so the app can do distance
-- filtering and map placement entirely in the client or via PostGIS later.
-- ---------------------------------------------------------------------------
create table public.restaurants (
    id           uuid primary key default uuid_generate_v4(),
    name         text not null,
    description  text,
    county       text not null,
    latitude     double precision not null check (latitude between -90 and 90),
    longitude    double precision not null check (longitude between -180 and 180),
    phone        text not null,
    created_at   timestamptz default now() not null
);

-- Helpful indexes
create index idx_restaurants_county     on public.restaurants (county);
create index idx_restaurants_lat_lon    on public.restaurants (latitude, longitude);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
alter table public.restaurants enable row level security;

-- Public: full read access
create policy "public_read"
    on public.restaurants
    for select
    to public
    using (true);

-- Service role: full access (used by Supabase backend / edge functions)
-- (Supabase bypasses RLS for service_role automatically, so this policy is
-- technically optional, but it documents intent explicitly.)
create policy "service_role_all"
    on public.restaurants
    for all
    to service_role
    using (true)
    with check (true);

-- Deny every other write operation from the public role
create policy "no_public_insert"
    on public.restaurants
    for insert
    to public
    with check (false);

create policy "no_public_update"
    on public.restaurants
    for update
    to public
    using (false);

create policy "no_public_delete"
    on public.restaurants
    for delete
    to public
    using (false);
