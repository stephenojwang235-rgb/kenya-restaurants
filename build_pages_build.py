#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_pages_build.py
====================
Regenerates the deploy-ready GitHub Pages build (`pages_build/`) from the
canonical source (`templates/index.html`).

Why this exists
---------------
The hand-edited `pages_build/index.html` had two problems:
  1. Emoji characters were corrupted (mozjibake) because the file was saved
     with the wrong encoding (a UTF-8 BOM was present and emojis like
     `📥` were stored as `ðŸ“¥`).
  2. It can silently drift out of sync with the real app.

Instead of maintaining a duplicate file by hand, this script derives
`pages_build/index.html` from the single source of truth
(`templates/index.html`) and swaps the Flask-style absolute asset paths
(`/static/...`) for the relative ones GitHub Pages needs (`static/...`).

Run it any time you change the app:
    python build_pages_build.py

It updates ONLY `pages_build/index.html`; the static assets (script.js,
config.js, style.css) and supabase_setup.sql are copied as-is if missing.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("build_pages")

ROOT = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(ROOT, "templates", "index.html")
OUT_INDEX = os.path.join(ROOT, "pages_build", "index.html")
OUT_DIR = os.path.join(ROOT, "pages_build")
# GitHub Pages serves from the repo ROOT of `main`, so the entry HTML must
# also exist at the repository root (the root `static/` folder is already
# deployed, and the generated page uses relative `static/...` paths).
OUT_ROOT_INDEX = os.path.join(ROOT, "index.html")

# Static assets that should live inside the build (copied if missing).
STATIC_ASSETS = ["script.js", "config.js", "style.css"]
EXTRA_FILES = ["supabase_setup.sql", "README.md"]


def path_for_out(filename: str) -> str:
    return os.path.join(OUT_DIR, "static", filename)


def sync_static() -> None:
    """Ensure the build's static/ folder mirrors the live static/ folder."""
    os.makedirs(os.path.join(OUT_DIR, "static"), exist_ok=True)  # ensure static/ exists
    for asset in STATIC_ASSETS:
        src = os.path.join(ROOT, "static", asset)
        dst = path_for_out(asset)
        if os.path.exists(src):
            if not os.path.exists(dst) or open(src, "rb").read() != open(dst, "rb").read():
                shutil.copy2(src, dst)
                logger.info("Synced static/%s", asset)
            else:
                logger.info("static/%s already up to date", asset)
        else:
            logger.warning("Missing source asset static/%s", asset)


def build_index() -> str:
    """Read the clean template, convert absolute paths to relative, return HTML."""
    with open(TEMPLATE, "r", encoding="utf-8-sig") as fh:
        html = fh.read()
    # GitHub Pages hosts project sites under /<repo>/ — use relative paths.
    html = html.replace('href="/static/', 'href="static/')
    html = html.replace('src="/static/', 'src="static/')
    return html


def main() -> None:
    if not os.path.exists(TEMPLATE):
        logger.error("Template not found: %s", TEMPLATE)
        sys.exit(1)

    sync_static()

    html = build_index()
    os.makedirs(OUT_DIR, exist_ok=True)
    # Write as clean UTF-8 WITHOUT BOM to avoid the encoding corruption issue.
    with open(OUT_INDEX, "w", encoding="utf-8", newline="") as fh:
        fh.write(html)

    # Also publish the same page at the repo root — GitHub Pages serves the
    # root of `main`, so `index.html` must exist there for the site to load.
    with open(OUT_ROOT_INDEX, "w", encoding="utf-8", newline="") as fh:
        fh.write(html)

    # Also make sure the extra deploy files exist in the build.
    for extra in EXTRA_FILES:
        src = os.path.join(ROOT, extra)
        dst = os.path.join(OUT_DIR, extra)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
            logger.info("Copied %s", extra)

    logger.info("Wrote %s (%d bytes, UTF-8 no BOM)", OUT_INDEX, len(html.encode("utf-8")))
    logger.info("Wrote %s (repo-root entry point for GitHub Pages)", OUT_ROOT_INDEX)
    logger.info("Done. Ready to upload the contents of pages_build/ to GitHub Pages.")


if __name__ == "__main__":
    main()
