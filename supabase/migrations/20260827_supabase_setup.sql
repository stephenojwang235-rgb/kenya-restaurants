-- ============================================================================
-- Kenya Restaurant Finder — Supabase setup (SINGLE FILE, run once)
-- Paste this whole file into the Supabase dashboard -> SQL Editor -> Run.
-- It creates the `restaurants` table used to store every restaurant the app
-- finds (restaurants WITHOUT a website), with security rules that only allow
-- reading and saving restaurants — nothing else.
-- NOTE: This replaces/supersedes the two older migration files in this folder.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Table
--    osm_id is unique so re-finding the same restaurant UPDATES the row
--    instead of creating duplicates.
-- ----------------------------------------------------------------------------
create table if not exists public.restaurants (
    id          bigint generated always as identity primary key,
    osm_id      text unique,                                -- OpenStreetMap id, e.g. "node-123456"
    name        text not null,
    county      text,
    address     text,
    description text,                                       -- cuisine / notes
    phone       text,                                       -- normalized +254...
    latitude    double precision not null check (latitude  between -90  and 90),
    longitude   double precision not null check (longitude between -180 and 180),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

-- ----------------------------------------------------------------------------
-- 2. Indexes
-- ----------------------------------------------------------------------------
create index if not exists idx_restaurants_county   on public.restaurants (county);
create index if not exists idx_restaurants_location on public.restaurants (latitude, longitude);
create index if not exists idx_restaurants_name     on public.restaurants (name);

-- ----------------------------------------------------------------------------
-- 3. Row Level Security — anonymous (browser) access
--    Read: everyone. Write: insert/update only (needed for upsert).
--    Delete: NOT allowed.
-- ----------------------------------------------------------------------------
alter table public.restaurants enable row level security;

drop policy if exists "anon_read_restaurants"   on public.restaurants;
drop policy if exists "anon_insert_restaurants" on public.restaurants;
drop policy if exists "anon_update_restaurants" on public.restaurants;

create policy "anon_read_restaurants"
    on public.restaurants for select
    to anon, authenticated
    using (true);

create policy "anon_insert_restaurants"
    on public.restaurants for insert
    to anon, authenticated
    with check (true);

create policy "anon_update_restaurants"
    on public.restaurants for update
    to anon, authenticated
    using (true)
    with check (true);

-- ----------------------------------------------------------------------------
-- 4. Privileges (needed for the browser/anon role to insert + upsert)
-- ----------------------------------------------------------------------------
grant select, insert, update on table public.restaurants to anon, authenticated;
grant usage, select on all sequences in schema public to anon, authenticated;

-- ----------------------------------------------------------------------------
-- 5. Keep updated_at fresh
-- ----------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_restaurants_updated_at on public.restaurants;
create trigger trg_restaurants_updated_at
    before update on public.restaurants
    for each row execute function public.set_updated_at();
