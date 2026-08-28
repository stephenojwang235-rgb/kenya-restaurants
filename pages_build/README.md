# Kenya Restaurant Finder — GitHub Pages Build

This folder is a **ready-to-upload static build** of the app. It works exactly like the
local version — live map, GPS tracking, and Supabase cloud saving — all in the browser.
No server needed.

## Contents
- `index.html` — the app (entry point)
- `static/` — style.css, script.js, config.js
- `supabase_setup.sql` — create the Supabase `restaurants` table (if not done yet)

## Deploy to GitHub Pages (no git required)

1. Log in at **https://github.com** and create a new repository:
   - Green **New** button → Name it `kenya-restaurants` → **Create repository**
   - For a personal site you can also name it exactly `<your-username>.github.io`.

2. Upload this folder's files to the repo **without the folder itself**:
   - In the repo click **"uploading an existing file"** link
   - **Drag-and-drop** the **contents** of this folder (index.html and the `static` folder)
   - Add a commit message → **Commit changes**

3. Turn on Pages:
   - Repo → **Settings** (gear, far right) → left menu → **Pages**
   - Under **Build and deployment** → **Source**: select **Deploy from a branch**
   - **Branch**: `main` → `/ (root)` → **Save**

4. Wait ~1 minute for the build. Your live URL is shown at the top of the same page —
   usually `https://<username>.github.io/kenya-restaurants/`.

> Tip: hold **Ctrl+F5** (hard refresh) on the live site after deploying so your browser
> uses the newest files.

## Notes
- Relative asset paths are used (`static/...`), so the site works from sub-folder URLs.
- Your Supabase keys are already in `static/config.js`.
- If you haven't run the SQL migration yet, paste `supabase_setup.sql` into the Supabase
  dashboard → SQL Editor and **Run** once.