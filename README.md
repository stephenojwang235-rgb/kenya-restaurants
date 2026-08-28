# Kenya Restaurant Finder — Live Map

> **🌐 Live site:** https://stephenojwang235-rgb.github.io/kenya-restaurants/

An interactive map that finds restaurants **near your real-time location** that don't yet have a website, using a fully live, free mapping stack (Leaflet + OpenStreetMap Overpass API).

---

## Features

- **Live interactive map** powered by Leaflet.js with OpenStreetMap's free public tiles
- **Real-time geolocation** via the browser's `navigator.geolocation` API
- **Manual location search** — search for any town, city, or neighborhood in Kenya using Nominatim geocoding
- **Kenya County dropdown** — quickly select from all 47 Kenyan counties for broader searches
- **Live Overpass queries** — a client-side `POST` fetch hits the public Overpass interpreter on demand
- Finds restaurants **without a website** within ~5 km of your position (`["website"!~"."]` filter)
- Extract WhatsApp/phone numbers (prioritizing `contact:whatsapp` tag)
- **Excel export** — download all found restaurants to a spreadsheet with one click
- Map markers for every result, with popups showing name, address, and phone
- "Use Current GPS Location" button (uses your device location)
- "Search Location" button (finds restaurants anywhere in Kenya)
- "Search County" button (zooms to selected Kenyan county)
- "Refresh Here" button (re-queries the current map center)
- **🛰️ Live GPS Tracking** — continuously follows your device GPS and automatically re-searches for restaurants when you move ~800 m (pure browser geolocation, no API keys)
- **☁️ Supabase cloud database** — every restaurant found is saved/updated automatically to your free Supabase project (duplicates merged by OpenStreetMap ID)

## How It Works

1. The Flask backend only serves the page and static assets.
2. **Use GPS**: Click "Use Current GPS Location" to get your device location via `navigator.geolocation.getCurrentPosition`, or **Search manually**: Enter a town/city name in Kenya to geocode it via Nominatim.
3. The map centers on the coordinates and issues a live Overpass QL query:
   ```
   [out:json][timeout:25];
   (
     node["amenity"="restaurant"]["website"!~"."](around:5000, LAT, LON);
     way["amenity"="restaurant"]["website"!~"."](around:5000, LAT, LON);
   );
   out body geom;
   ```
4. Returned restaurants without websites are plotted as Leaflet markers and listed below the map.

No API keys, no database, no server-side caching — the data is always live from OpenStreetMap.

## Quick Start

### Start on This Computer
Double-click **START_SERVER.bat**
- Server starts automatically
- Browser opens to http://localhost:5000
- Click **📍 Use Current GPS Location** to use your device location, or enter a town/city name in the search bar to explore anywhere in Kenya

### Access from Android Phone
1. Double-click **SETUP_ANDROID.bat** (or **GET_IP.bat**) on your computer
2. Ensure your phone is on the SAME WiFi network
3. On your phone, open `http://[YOUR_IP]:5000`
4. Tap Chrome menu (3 dots) → "Add to Home screen"

### Auto-Start on Windows Login
1. Right-click **INSTALL_AUTO_START.bat**
2. Select "Run as administrator"
3. The app starts automatically when you log into Windows

## Supabase Cloud Database (Save the Restaurants You Find)

All restaurants discovered by the app can be stored in a **free Supabase** project. One-time setup:

### Step 1 — Create a free Supabase project
1. Go to **https://supabase.com** → **Start your project** → sign up (free)
2. Click **New project**
   - Name: `kenya-restaurants`
   - Database Password: click **Generate a password** and save it somewhere safe
   - Region: choose the one closest to Kenya (e.g. **Frankfurt / EU Central**)
3. Click **Create new project** and wait ~2 minutes for it to provision

### Step 2 — Create the table
1. In the Supabase dashboard open **SQL Editor** → **New query**
2. Paste the entire contents of `supabase/migrations/20260827_supabase_setup.sql`
3. Click **Run** — this creates the `restaurants` table, indexes, and security rules
   (Note: this single file supersedes the two older `.sql` files in `supabase/migrations/`.)

### Step 3 — Connect the app
1. In the dashboard go to **Project Settings (⚙️) → Data API** (or "API Keys")
2. Copy the **Project URL** and the **anon public** key
3. Open `static/config.js` in this folder and paste them:
   ```js
   window.SUPABASE_CONFIG = {
       url: 'https://YOUR-PROJECT-REF.supabase.co',
       anonKey: 'YOUR-ANON-PUBLIC-KEY-HERE',
   };
   ```
4. Restart the server (START_SERVER.bat) and refresh the page

Done! From now on:
- Every search **auto-saves** the restaurants it finds to Supabase (or press **☁️ Save to Supabase** manually)
- Duplicates are merged automatically via the unique `osm_id` column — phone numbers and names get updated
- The **anon key is a public key** — it's designed to be used in browsers and is safe to expose. Security rules allow only reading and inserting/updating restaurants, never deleting.

To view your data: Supabase dashboard → **Table Editor** → `restaurants`.
To export from Supabase: Table Editor → **Export CSV**.

## Files in This Folder

- **START_SERVER.bat** - Start the app on this computer
- **GET_IP.bat** - Get your computer's IP for network access
- **SETUP_ANDROID.bat** - Set up access from Android phone
- **INSTALL_AUTO_START.bat** - Make app start on Windows login
- **server.py** - Minimal Flask server (serves page + static files)
- **templates/index.html** - Page with Leaflet map
- **static/script.js** - Geolocation, live Overpass fetch, marker rendering, Supabase saving, live tracking
- **static/config.js** - Supabase Project URL + anon key (paste yours here)
- **static/style.css** - Styling
- **pages_build/** - Static build for the hosted site (GitHub Pages)
- **build_pages_build.py** - Regenerates `pages_build/` from `templates/` + `static/`
- **supabase/migrations/20260827_supabase_setup.sql** - Creates the `restaurants` table
- **stealth_scraper.py** - Optional stealth scraper with multi-source phone-number fallback
- **README.md** - This file

## Deployment (GitHub Pages)

The public site is hosted with **GitHub Pages** from the `main` branch root:
`https://stephenojwang235-rgb.github.io/kenya-restaurants/`

To update the hosted site after making changes to `templates/` or `static/`:

```bash
python build_pages_build.py   # regenerate pages_build/index.html from the source
git add -A
git commit -m "update site"
git push origin main
```

GitHub Pages rebuilds automatically within a minute or two.

## License

No license specified — all rights reserved by default. Open an issue or contact the maintainer if you'd like to use this project.

## Troubleshooting

### App won't start:
- Make sure Python is installed
- Run: `pip install flask waitress`
- Double-click START_SERVER.bat again

### Location not working:
- Browsers only allow geolocation on `https://` or `http://localhost` / local network IPs.
- If permission is denied, you can still pan the map manually and click "Refresh Here".

### No restaurants found:
- The public Overpass API can be busy; wait a moment and click "Refresh Here" again.
- Try panning to a denser urban area.

### Can't access from phone:
- Ensure phone and computer are on the same WiFi
- Check firewall allows Python on port 5000

## Technical Details

- **Backend**: Flask with Waitress production server (serves static files only)
- **Map**: Leaflet.js + OpenStreetMap public tiles
- **Geocoding**: OpenStreetMap Nominatim API for location search
- **Data**: OpenStreetMap Overpass API (`https://overpass-api.de/api/interpreter`), queried live from the browser via `POST`
- **Frontend**: Vanilla HTML/CSS/JavaScript (Leaflet loaded from CDN)
- **Search radius**: 5 km from the query point

## Project Location

`c:\Users\PC\OneDrive\Desktop\restaurant website\`
