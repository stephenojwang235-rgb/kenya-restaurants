/* ============================================================
   Kenya Restaurant Finder — App Script
   Uses Overpass API (OpenStreetMap) + Leaflet.js
   ============================================================ */

// ---- State ----
let map = null;
let markerLayer = null;
let restaurantMarkers = {};   // id -> L.marker
let currentRestaurants = [];  // full dataset from Overpass
let activeCardId = null;      // currently highlighted card
let currentSearchCenter = null; // {lat, lng} of last search

// Supabase cloud storage state
let supabaseClient = null;    // Supabase JS client
let supabaseEnabled = false;  // true when config.js has valid keys

// Live GPS tracking state (browser geolocation — no API keys)
let liveTracking = false;     // tracking on/off
let liveWatchId = null;       // watchPosition handle
let youMarker = null;         // "You are here" marker
let youAccuracy = null;       // accuracy circle around your position
let lastQueryPoint = null;    // {lat, lng} of last Overpass query

// ---- DOM References ----
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ---- Constants ----
// Primary Overpass server. Sometimes overloaded (returns 504) — we fail over
// to the mirrors listed in OVERPASS_URLS below.
const OVERPASS_URL = 'https://overpass-api.de/api/interpreter';
const NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search';
const SEARCH_RADIUS = 5000; // 5 km in meters

// Overpass public mirrors (main + alternates). If one returns 504/429 or a
// network error, the app automatically retries on the next available mirror.
const OVERPASS_URLS = [
    'https://overpass-api.de/api/interpreter',            // main (osm wiki)
    'https://overpass.kumi.systems/api/interpreter',      // Kumi Systems
    'https://overpass.private.coffee/api/interpreter',    // private.coffee
    'https://maps.mail.ru/osm/tools/overpass/api/interpreter', // Mail.ru OSM
    'https://overpass.osm.jp/api/interpreter',            // Japan mirror
    'https://overpass.nchc.org.tw/api/interpreter',       // Taiwan NCHC mirror
];
const OVERPASS_TIMEOUT_MS = 45000; // per-request wait before giving up
const OVERPASS_RETRY_DELAY_MS = 1200; // pause between mirror attempts (be polite)

// Supabase / live tracking constants
const SUPABASE_TABLE = 'restaurants';
const SUPABASE_BATCH_SIZE = 100;
const LIVE_RERUN_DISTANCE = 800; // meters — auto re-query when you move this far

// ==============================================================
// INIT
// ==============================================================
document.addEventListener('DOMContentLoaded', () => {
    initSupabase();
    initMap();
    bindEvents();
});

// ==============================================================
// LEAFLET MAP
// ==============================================================
function initMap() {
    // Center on Kenya
    map = L.map('map', {
        center: [-0.286389, 36.817223],
        zoom: 6,
        zoomControl: true,
        attributionControl: true,
    });

    // OpenStreetMap tiles
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution:
            '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    // Layer group for restaurant markers
    markerLayer = L.layerGroup().addTo(map);
}

// ==============================================================
// EVENT BINDING
// ==============================================================
function bindEvents() {
    // GPS button
    const gpsBtn = document.getElementById('btn-gps');
    if (gpsBtn) {
        gpsBtn.addEventListener('click', useGPS);
    }

    // Search button
    const searchBtn = document.getElementById('btn-search');
    if (searchBtn) {
        searchBtn.addEventListener('click', searchLocation);
    }

    // Search input - Enter key
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') searchLocation();
        });
    }

    // Search County button
    const searchCountyBtn = document.getElementById('btn-search-county');
    if (searchCountyBtn) {
        searchCountyBtn.addEventListener('click', searchCounty);
    }

    // County dropdown - also trigger on change
    const countySelect = document.getElementById('county-select');
    if (countySelect) {
        countySelect.addEventListener('change', (e) => {
            if (e.target.value) searchCounty();
        });
    }

    // "Fit All" button
    const fitBtn = document.getElementById('btn-locate-all');
    if (fitBtn) {
        fitBtn.addEventListener('click', fitMapToMarkers);
    }

    // Export to Excel button
    const exportBtn = document.getElementById('btn-export-excel');
    if (exportBtn) {
        exportBtn.addEventListener('click', exportToExcel);
    }

    // Refresh button
    const refreshBtn = document.getElementById('btn-refresh');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', refreshHere);
    }

    // Mobile sidebar toggle
    const toggleBtn = document.getElementById('sidebar-toggle');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            const sidebar = document.getElementById('sidebar');
            sidebar.classList.toggle('collapsed');
        });
    }

    // Live GPS tracking toggle (no API keys — browser geolocation only)
    const liveBtn = document.getElementById('btn-live');
    if (liveBtn) {
        liveBtn.addEventListener('click', toggleLiveTracking);
    }

    // Manual save to Supabase cloud database
    const saveDbBtn = document.getElementById('btn-save-db');
    if (saveDbBtn) {
        saveDbBtn.addEventListener('click', () => saveToSupabase(false));
    }
}

// ==============================================================
// GPS GEOLOCATION
// ==============================================================
function useGPS() {
    if (!navigator.geolocation) {
        setStatus('Geolocation is not supported by your browser.', 'error');
        return;
    }

    setStatus('Getting your location...', 'info');

    navigator.geolocation.getCurrentPosition(
        (position) => {
            const lat = position.coords.latitude;
            const lng = position.coords.longitude;
            currentSearchCenter = { lat, lng };
            map.setView([lat, lng], 14);
            setStatus(`📍 Located! Searching for restaurants nearby...`, 'info');
            queryOverpass(lat, lng);
        },
        (error) => {
            let msg = 'Failed to get location.';
            if (error.code === 1) msg = 'Location permission denied. Please allow location access.';
            else if (error.code === 2) msg = 'Location unavailable. Try again.';
            else if (error.code === 3) msg = 'Location request timed out. Try again.';
            setStatus(msg, 'error');
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
    );
}

// ==============================================================
// SEARCH LOCATION (Nominatim Geocoding)
// ==============================================================
async function searchLocation() {
    const input = document.getElementById('search-input');
    const query = input ? input.value.trim() : '';
    if (!query) {
        setStatus('Please enter a town or city name.', 'error');
        return;
    }

    setStatus(`Searching for "${query}"...`, 'info');

    try {
        const url = `${NOMINATIM_URL}?q=${encodeURIComponent(query)},+Kenya&format=json&limit=1`;
        const resp = await fetch(url, {
            headers: { 'Accept-Language': 'en' }
        });
        const data = await resp.json();

        if (!data || data.length === 0) {
            setStatus(`Location "${query}" not found. Try a different name.`, 'error');
            return;
        }

        const lat = parseFloat(data[0].lat);
        const lng = parseFloat(data[0].lon);
        const displayName = data[0].display_name.split(',')[0];

        currentSearchCenter = { lat, lng };
        map.setView([lat, lng], 14);
        setStatus(`📍 ${displayName} — Searching for restaurants...`, 'info');
        queryOverpass(lat, lng);
    } catch (err) {
        setStatus('Search failed: ' + err.message, 'error');
    }
}

// ==============================================================
// SEARCH COUNTY
// ==============================================================
async function searchCounty() {
    const select = document.getElementById('county-select');
    const county = select ? select.value : '';
    if (!county) {
        setStatus('Please select a county.', 'error');
        return;
    }

    setStatus(`Searching for ${county} county...`, 'info');

    try {
        // Geocode the county to get its center
        const url = `${NOMINATIM_URL}?q=${encodeURIComponent(county)}+County,+Kenya&format=json&limit=1`;
        const resp = await fetch(url, {
            headers: { 'Accept-Language': 'en' }
        });
        const data = await resp.json();

        if (!data || data.length === 0) {
            setStatus(`Could not find ${county} county.`, 'error');
            return;
        }

        const lat = parseFloat(data[0].lat);
        const lng = parseFloat(data[0].lon);

        currentSearchCenter = { lat, lng };
        map.setView([lat, lng], 10);
        setStatus(`📍 ${county} — Searching for restaurants...`, 'info');
        queryOverpass(lat, lng);
    } catch (err) {
        setStatus('County search failed: ' + err.message, 'error');
    }
}

// ==============================================================
// REFRESH HERE
// ==============================================================
function refreshHere() {
    const center = map.getCenter();
    currentSearchCenter = { lat: center.lat, lng: center.lng };
    setStatus('Refreshing restaurants in this area...', 'info');
    queryOverpass(center.lat, center.lng);
}

// ==============================================================
// OVERPASS API QUERY
// ==============================================================

/**
 * POST a query to Overpass, trying each public mirror in turn.
 * Automatically retries on another server if one returns 504 (busy),
 * 429 (rate limited), a non-OK status, or a network error/timeout.
 * Returns { ok:true, data, usedUrl } on success, or { ok:false, error }.
 */
async function fetchOverpass(query) {
    let lastError = '';

    for (let i = 0; i < OVERPASS_URLS.length; i++) {
        const url = OVERPASS_URLS[i];
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), OVERPASS_TIMEOUT_MS);

        try {
            const resp = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: 'data=' + encodeURIComponent(query),
                signal: controller.signal,
            });
            clearTimeout(timer);

            if (resp.ok) {
                return { ok: true, data: await resp.json(), usedUrl: url };
            }

            // Mirror responded but the query failed on it
            lastError = `${url} -> ${resp.status} ${resp.statusText}`;
        } catch (err) {
            clearTimeout(timer);
            lastError = err.name === 'AbortError'
                ? `${url} -> timeout`
                : `${url} -> ${err.message}`;
        }

        // Looping past the last mirror? We're out of options.
        if (i === OVERPASS_URLS.length - 1) break;

        // Brief pause before trying the next mirror (be polite to each server)
        await new Promise((r) => setTimeout(r, OVERPASS_RETRY_DELAY_MS + i * 300));
    }

    return { ok: false, error: lastError };
}

async function queryOverpass(lat, lng) {
    showSkeleton(true);
    lastQueryPoint = { lat: lat, lng: lng };

    // Overpass QL query: find restaurants without a website within 5km
    const overpassQuery = `
        [out:json][timeout:25];
        (
          node["amenity"="restaurant"]["website"!~"."](around:${SEARCH_RADIUS}, ${lat}, ${lng});
          way["amenity"="restaurant"]["website"!~"."](around:${SEARCH_RADIUS}, ${lat}, ${lng});
        );
        out body geom;
    `;

    try {
        const result = await fetchOverpass(overpassQuery);

        if (!result.ok) {
            setStatus(
                'Overpass is busy right now (504). Please wait a few seconds and click 🔄 Refresh Here.',
                'error'
            );
            console.warn('[Overpass] All mirrors failed:', result.error);
            showSkeleton(false);
            return;
        }

        const data = result.data;
        const elements = data.elements || [];

        // Convert Overpass elements to our restaurant format
        const restaurants = elements.map((el, index) => {
            const tags = el.tags || {};
            const name = tags.name || tags['name:en'] || `Restaurant #${index + 1}`;
            const phone = tags['contact:whatsapp'] || tags['contact:phone'] || tags.phone || '';
            const description = tags.cuisine || tags.description || '';

            let lat2, lng2;
            if (el.type === 'node') {
                lat2 = el.lat;
                lng2 = el.lon;
            } else if (el.type === 'way' && el.geometry && el.geometry.length > 0) {
                // Use center of way geometry
                const center = getCenterOfGeometry(el.geometry);
                lat2 = center.lat;
                lng2 = center.lng;
            } else {
                return null;
            }

            return {
                id: el.type + '-' + el.id,
                name: name,
                description: description,
                county: tags.county || tags['addr:county'] || tags['is_in:county'] || '',
                latitude: lat2,
                longitude: lng2,
                phone: phone,
                address: tags['addr:full'] || tags['addr:street'] || ''
            };
        }).filter(r => r !== null);

        currentRestaurants = restaurants;
        renderList(currentRestaurants);
        renderMarkers(currentRestaurants);
        fitMapToMarkers();

        const count = currentRestaurants.length;
        setStatus(
            `Found ${count} restaurant${count !== 1 ? 's' : ''} without websites nearby.`,
            count > 0 ? 'success' : 'info'
        );

        // Auto-save everything found to the Supabase cloud database
        if (supabaseEnabled && count > 0) {
            await saveToSupabase(true);
        }
    } catch (err) {
        setStatus('Network error: ' + err.message, 'error');
    } finally {
        showSkeleton(false);
    }
}

/** Calculate the center point of a polygon/line geometry */
function getCenterOfGeometry(geometry) {
    let latSum = 0, lngSum = 0, count = 0;
    for (const pt of geometry) {
        latSum += pt.lat;
        lngSum += pt.lon;
        count++;
    }
    return { lat: latSum / count, lng: lngSum / count };
}

// ==============================================================
// RENDER — RESTAURANT LIST (LEFT SIDEBAR)
// ==============================================================
function renderList(restaurants) {
    const list = document.getElementById('results-list');
    if (!list) return;

    list.innerHTML = '';

    if (restaurants.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.innerHTML = `
            <span class="empty-icon">🍽️</span>
            <div class="empty-title">No restaurants found</div>
            <div>Try a different location or county.</div>
        `;
        list.appendChild(empty);
        return;
    }

    restaurants.forEach((r) => {
        const card = document.createElement('div');
        card.className = 'restaurant-card';
        card.dataset.id = r.id;

        // --- Name ---
        const title = document.createElement('div');
        title.className = 'restaurant-name';
        title.textContent = r.name;

        // --- County / Address ---
        const location = document.createElement('div');
        location.className = 'restaurant-county';
        location.textContent = r.county || r.address || '';

        // --- Description (cuisine) ---
        let desc = null;
        if (r.description) {
            desc = document.createElement('div');
            desc.className = 'restaurant-description';
            desc.textContent = r.description;
        }

        // --- Actions ---
        const actions = document.createElement('div');
        actions.className = 'restaurant-actions';

        const whatsappBtn = document.createElement('a');
        whatsappBtn.className = 'btn-whatsapp';
        whatsappBtn.href = buildWhatsAppLink(r.phone);
        whatsappBtn.target = '_blank';
        whatsappBtn.rel = 'noopener noreferrer';
        whatsappBtn.textContent = r.phone ? 'Chat on WhatsApp' : 'No Phone';

        const locateBtn = document.createElement('button');
        locateBtn.className = 'btn-locate';
        locateBtn.textContent = '📍 Locate';
        locateBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            centerOnRestaurant(r);
        });

        actions.appendChild(whatsappBtn);
        actions.appendChild(locateBtn);

        // --- Assemble card ---
        card.appendChild(title);
        card.appendChild(location);
        if (desc) card.appendChild(desc);
        card.appendChild(actions);

        // Click card -> center map on this restaurant
        card.addEventListener('click', () => {
            centerOnRestaurant(r);
        });

        list.appendChild(card);
    });
}

// ==============================================================
// RENDER — MAP MARKERS
// ==============================================================
function renderMarkers(restaurants) {
    markerLayer.clearLayers();
    restaurantMarkers = {};

    restaurants.forEach((r) => {
        const lat = parseFloat(r.latitude);
        const lng = parseFloat(r.longitude);

        if (isNaN(lat) || isNaN(lng)) return;

        const marker = L.marker([lat, lng]).addTo(markerLayer);

        // Build popup HTML
        const phoneDisplay = r.phone || 'No phone';
        const phoneLink = buildWhatsAppLink(r.phone);
        const descHtml = r.description
            ? `<div class="popup-desc">${escapeHtml(r.description)}</div>`
            : '';
        const addrHtml = r.address
            ? `<div class="popup-addr">📍 ${escapeHtml(r.address)}</div>`
            : '';

        const popupHtml = `
            <div class="popup-name">${escapeHtml(r.name)}</div>
            ${addrHtml}
            ${descHtml}
            <a class="popup-whatsapp" href="${phoneLink}" target="_blank" rel="noopener noreferrer">
                💬 ${escapeHtml(phoneDisplay)}
            </a>
        `;

        marker.bindPopup(popupHtml, { maxWidth: 260 });

        // Store reference
        restaurantMarkers[r.id] = marker;
    });
}

// ==============================================================
// MAP INTERACTION
// ==============================================================

/** Fly to a restaurant's marker and open its popup */
function centerOnRestaurant(r) {
    const marker = restaurantMarkers[r.id];
    if (!marker) return;

    const latlng = marker.getLatLng();
    map.flyTo(latlng, 16, { duration: 0.8 });
    marker.openPopup();

    // Highlight the card in the sidebar
    highlightCard(r.id);
}

/** Highlight a card by ID, scroll it into view */
function highlightCard(id) {
    // Remove previous active state
    if (activeCardId) {
        const prev = document.querySelector(
            `.restaurant-card[data-id="${activeCardId}"]`
        );
        if (prev) prev.classList.remove('active');
    }

    activeCardId = id;

    const card = document.querySelector(
        `.restaurant-card[data-id="${id}"]`
    );
    if (card) {
        card.classList.add('active');
        card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

/** Fit the map view to show all markers */
function fitMapToMarkers() {
    const markerIds = Object.keys(restaurantMarkers);
    if (markerIds.length === 0) {
        // Default to Kenya view
        map.setView([-0.286389, 36.817223], 6);
        return;
    }

    const group = L.featureGroup(
        markerIds.map((id) => restaurantMarkers[id])
    );
    map.fitBounds(group.getBounds().pad(0.1), { maxZoom: 14 });
}

// ==============================================================
// HELPERS
// ==============================================================

/** Build a WhatsApp deep link from a phone number */
function buildWhatsAppLink(phone) {
    if (!phone) return 'https://wa.me/254700000000';
    const digits = phone.replace(/[^0-9]/g, '');
    return `https://wa.me/${digits}`;
}

/** Update the status bar */
function setStatus(msg, type = 'info') {
    const el = document.getElementById('status');
    if (!el) return;

    const icon = el.querySelector('.status-icon');
    const text = el.querySelector('.status-text');

    // Reset classes
    el.className = 'status-msg';

    if (type === 'error') {
        el.classList.add('error');
        if (icon) icon.textContent = '❌';
    } else if (type === 'success') {
        el.classList.add('success');
        if (icon) icon.textContent = '✅';
    } else {
        if (icon) icon.textContent = 'ℹ️';
    }

    if (text) text.textContent = msg;
}

/** Show/hide the loading skeleton */
function showSkeleton(visible) {
    const list = document.getElementById('results-list');
    if (!list) return;

    let skeleton = list.querySelector('.loading-skeleton');
    if (visible) {
        if (!skeleton) {
            skeleton = document.createElement('div');
            skeleton.className = 'loading-skeleton';
            skeleton.innerHTML = `
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
            `;
            list.innerHTML = '';
            list.appendChild(skeleton);
        }
    } else {
        if (skeleton) skeleton.remove();
    }
}

/** Escape HTML to prevent XSS */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ==============================================================
// LIVE GPS TRACKING (browser geolocation — no API keys)
// ==============================================================

/** Toggle continuous GPS tracking with automatic re-search when you move */
function toggleLiveTracking() {
    const btn = document.getElementById('btn-live');

    // --- Stop tracking ---
    if (liveTracking) {
        if (liveWatchId !== null) navigator.geolocation.clearWatch(liveWatchId);
        liveWatchId = null;
        liveTracking = false;
        clearYouMarker();
        if (btn) {
            btn.textContent = '🛰️ Live Tracking: OFF';
            btn.classList.remove('live-on');
        }
        setStatus('Live tracking stopped.', 'info');
        return;
    }

    // --- Start tracking ---
    if (!navigator.geolocation) {
        setStatus('Geolocation is not supported by your browser.', 'error');
        return;
    }

    liveTracking = true;
    if (btn) {
        btn.textContent = '🛰️ Live Tracking: ON';
        btn.classList.add('live-on');
    }
    setStatus('Live tracking started — following your GPS position...', 'info');

    liveWatchId = navigator.geolocation.watchPosition(
        handleLivePosition,
        (error) => {
            let msg = 'Failed to get location.';
            if (error.code === 1) msg = 'Location permission denied. Please allow location access.';
            else if (error.code === 2) msg = 'Location unavailable.';
            else if (error.code === 3) msg = 'Location request timed out.';
            setStatus('Live tracking error: ' + msg, 'error');
            toggleLiveTracking(); // stop cleanly on failure
        },
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 5000 }
    );
}

/** Called on every GPS fix while live tracking is on */
function handleLivePosition(position) {
    const lat = position.coords.latitude;
    const lng = position.coords.longitude;
    const accuracy = position.coords.accuracy || 0;

    // Draw/update your live position on the map (pure browser GPS, no API keys)
    clearYouMarker();
    youMarker = L.circleMarker([lat, lng], {
        radius: 8,
        color: '#ffffff',
        weight: 2,
        fillColor: '#2563eb',
        fillOpacity: 1,
    }).addTo(map).bindPopup('📍 You are here (live)');

    if (accuracy > 0) {
        youAccuracy = L.circle([lat, lng], {
            radius: accuracy,
            color: '#2563eb',
            weight: 1,
            fillColor: '#2563eb',
            fillOpacity: 0.15,
        }).addTo(map);
    }

    currentSearchCenter = { lat: lat, lng: lng };

    // First GPS fix: center and search immediately
    if (!lastQueryPoint) {
        map.setView([lat, lng], 15);
        setStatus('📡 GPS locked — searching for restaurants near you...', 'info');
        queryOverpass(lat, lng);
        return;
    }

    // Auto re-query once you move beyond the threshold (e.g. driving around)
    const moved = distanceMeters(lastQueryPoint.lat, lastQueryPoint.lng, lat, lng);
    if (moved >= LIVE_RERUN_DISTANCE) {
        setStatus(`📡 You moved ~${Math.round(moved)} m — refreshing nearby restaurants...`, 'info');
        map.panTo([lat, lng]);
        queryOverpass(lat, lng);
    }
}

/** Remove the "you are here" marker and accuracy circle */
function clearYouMarker() {
    if (youMarker) { map.removeLayer(youMarker); youMarker = null; }
    if (youAccuracy) { map.removeLayer(youAccuracy); youAccuracy = null; }
}

/** Haversine distance between two points, in meters */
function distanceMeters(lat1, lng1, lat2, lng2) {
    const R = 6371000; // Earth radius in meters
    const toRad = (d) => (d * Math.PI) / 180;
    const dLat = toRad(lat2 - lat1);
    const dLng = toRad(lng2 - lng1);
    const a =
        Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
        Math.sin(dLng / 2) * Math.sin(dLng / 2);
    return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// ==============================================================
// SUPABASE CLOUD DATABASE
// ==============================================================

/** Create the Supabase client from static/config.js (URL + anon key) */
function initSupabase() {
    const cfg = window.SUPABASE_CONFIG || {};
    const url = (cfg.url || '').trim();
    const anonKey = (cfg.anonKey || '').trim();

    if (!url || !anonKey ||
        url.includes('YOUR-PROJECT') || anonKey.includes('YOUR-ANON')) {
        supabaseEnabled = false;
        console.warn(
            '[Supabase] Not configured. Paste your Project URL and anon key ' +
            'into static/config.js — see README "Supabase Cloud Database".'
        );
        return;
    }

    try {
        supabaseClient = supabase.createClient(url, anonKey, {
            auth: { persistSession: false },
        });
        supabaseEnabled = true;
        console.info('[Supabase] Connected — found restaurants will auto-save to the cloud.');
    } catch (err) {
        supabaseEnabled = false;
        console.error('[Supabase] Failed to initialize:', err.message);
    }
}

/** Normalize a phone number to international format (+254...) */
function normalizePhoneForDb(phone) {
    if (!phone) return null;
    let digits = phone.replace(/[^\d+]/g, '');
    if (digits.startsWith('+')) digits = digits.slice(1);
    if (digits.startsWith('0')) digits = '254' + digits.slice(1);
    if (digits.startsWith('7') || digits.startsWith('1')) digits = '254' + digits;
    return digits ? '+' + digits : null;
}

/** Upsert the currently loaded restaurants into Supabase (duplicates merged by osm_id) */
async function saveToSupabase(auto = false) {
    if (!supabaseEnabled) {
        if (!auto) {
            setStatus(
                'Supabase not configured — paste your Project URL and anon key into static/config.js, then refresh.',
                'error'
            );
        }
        return;
    }

    if (currentRestaurants.length === 0) {
        if (!auto) setStatus('No restaurants to save. Search a location first.', 'error');
        return;
    }

    const rows = currentRestaurants
        .map((r) => ({
            osm_id: r.id,
            name: r.name || 'Unnamed restaurant',
            county: r.county || null,
            address: r.address || null,
            description: r.description || null,
            phone: normalizePhoneForDb(r.phone),
            latitude: parseFloat(r.latitude),
            longitude: parseFloat(r.longitude),
        }))
        .filter((r) => !isNaN(r.latitude) && !isNaN(r.longitude));

    let saved = 0;
    for (let i = 0; i < rows.length; i += SUPABASE_BATCH_SIZE) {
        const batch = rows.slice(i, i + SUPABASE_BATCH_SIZE);
        const { error } = await supabaseClient
            .from(SUPABASE_TABLE)
            .upsert(batch, { onConflict: 'osm_id' });

        if (error) {
            console.error('[Supabase] Upsert failed:', error);
            setStatus('Cloud save failed: ' + error.message, 'error');
            return;
        }
        saved += batch.length;
    }

    const count = currentRestaurants.length;
    if (auto) {
        setStatus(
            `Found ${count} restaurant${count !== 1 ? 's' : ''} nearby. ` +
            `💾 ${saved} saved/updated in Supabase.`,
            'success'
        );
    } else {
        setStatus(
            `💾 ${saved} restaurant${saved !== 1 ? 's' : ''} saved/updated in Supabase cloud database.`,
            'success'
        );
    }
}

// ==============================================================
// EXCEL EXPORT
// ==============================================================

/** Export the currently loaded list to an .xlsx file and trigger download */
function exportToExcel() {
    if (currentRestaurants.length === 0) {
        setStatus('No restaurants to export.', 'error');
        return;
    }

    // Build worksheet data
    const rows = currentRestaurants.map((r) => ({
        'Restaurant Name': r.name || '',
        'County': r.county || '',
        'Address': r.address || '',
        'Cuisine': r.description || '',
        'Latitude': r.latitude != null ? parseFloat(r.latitude) : '',
        'Longitude': r.longitude != null ? parseFloat(r.longitude) : '',
        'WhatsApp Number': r.phone || '',
    }));

    // Create workbook
    const wb = XLSX.utils.book_new();
    const ws = XLSX.utils.json_to_sheet(rows);

    // Column widths (approximate character widths)
    ws['!cols'] = [
        { wch: 35 },  // Restaurant Name
        { wch: 18 },  // County
        { wch: 30 },  // Address
        { wch: 20 },  // Cuisine
        { wch: 12 },  // Latitude
        { wch: 12 },  // Longitude
        { wch: 20 },  // WhatsApp Number
    ];

    XLSX.utils.book_append_sheet(wb, ws, 'Restaurants');

    // Generate filename with timestamp
    const now = new Date();
    const dateStr = now.toISOString().split('T')[0];
    const filename = `kenya_restaurants_${dateStr}.xlsx`;

    // Trigger browser download
    XLSX.writeFile(wb, filename);

    setStatus(
        `Downloaded ${currentRestaurants.length} restaurant${currentRestaurants.length !== 1 ? 's' : ''}.`,
        'success'
    );
}