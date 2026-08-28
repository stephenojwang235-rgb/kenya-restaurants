#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_site.py
=====================================================================
Health check for the hosted Kenya Restaurant Finder site.

Why this exists
---------------
Right after a GitHub Pages redeploy the Fastly edge cache can briefly
serve stale content or a 404 for a few seconds to a couple of minutes.
That transient 404 is NOT a real outage — it disappears on its own —
but it looks alarming if you check immediately after pushing.

This script therefore:
  1. checks every important URL,
  2. retries with a short backoff before declaring a failure,
  3. verifies actual CONTENT (not just HTTP 200) — e.g. that the index
     really is our app (map div, GPS button, SEO tags) and not a Jekyll
     placeholder page.

Usage:
    python check_site.py
    python check_site.py --base https://youruser.github.io/kenya-restaurants/
    python check_site.py --retries 8 --wait 5

Exit code is 0 when healthy, 1 when any URL or content check fails.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.request
import urllib.error

DEFAULT_BASE = "https://stephenojwang235-rgb.github.io/kenya-restaurants/"

# (path, list of required-content-regexes, list of forbidden-content-markers)
CHECKS = [
    # The index must be OUR app: map + GPS button + SEO/structured-data
    # markers present, and no Jekyll placeholder markers.
    ("",
     [r'id="map"', r'btn-gps', r'og:title', r'og:image',
      r'application/ld\+json', r'<noscript>', r'name="robots"'],
     ["| kenya-restaurants", "skip-to-content"]),
    ("static/config.js", [r'supabase\.co'], []),
    ("static/script.js", [], []),
    ("static/style.css", [], []),
    ("static/og-image.png", [], []),
    ("static/manifest.webmanifest", [r'"name"'], []),
    ("robots.txt", [r'User-agent', r'[Ss]itemap'], []),
    ("sitemap.xml", [r'<urlset', r'<lastmod>'], []),
]


def fetch(url: str, timeout: int = 25) -> tuple[int, str]:
    """GET a URL, returning (status_code, body). Raises on network errors."""
    req = urllib.request.Request(url, headers={"User-Agent": "site-health-check/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except Exception as exc:  # network / TLS / DNS issues
        raise exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Health-check the hosted site")
    parser.add_argument("--base", default=DEFAULT_BASE, help="Base URL of the site")
    parser.add_argument("--retries", type=int, default=5, help="Attempts per URL")
    parser.add_argument("--wait", type=float, default=6.0, help="Seconds between attempts")
    args = parser.parse_args()

    base = args.base if args.base.endswith("/") else args.base + "/"
    failures = 0
    saw_transient_404 = False

    print(f"Checking {base}\n")

    for path, required_list, forbidden_list in CHECKS:
        url = base + path
        label = "/" + path if path else "/ (index)"

        for attempt in range(1, args.retries + 1):
            try:
                status, body = fetch(url)
            except Exception as exc:
                status, body = 0, ""
                print(f"  {label}: network error: {exc}")

            if status == 200:
                # Content validation.
                problems = []
                for pattern in required_list:
                    if not re.search(pattern, body):
                        problems.append(f"missing expected content ({pattern})")
                for bad in forbidden_list:
                    if bad in body:
                        problems.append(f"forbidden content detected ({bad!r})")
                if problems:
                    print(f"  {label}: HTTP 200 but CONTENT PROBLEM -> {'; '.join(problems)}")
                    failures += 1
                else:
                    print(f"  {label}: OK (200, {len(body)} bytes, content verified)")
                break

            if status == 404:
                saw_transient_404 = True
                print(f"  {label}: 404 (attempt {attempt}/{args.retries}) "
                      f"— likely CDN propagation; retrying...")
            else:
                print(f"  {label}: HTTP {status} (attempt {attempt}/{args.retries})")

            if attempt < args.retries:
                time.sleep(args.wait)
        else:
            print(f"  {label}: FAILED after {args.retries} attempts")
            failures += 1

    print()
    if failures == 0:
        print("RESULT: HEALTHY — all URLs return 200 with the expected content.")
        if saw_transient_404:
            print("(A transient 404 was seen and resolved by retrying — normal "
                  "right after a redeploy, not an outage.)")
        return 0

    print(f"RESULT: {failures} check(s) FAILED.")
    print("If only a 404 persists for several minutes, see the 'Deployment "
          "(GitHub Pages)' section of README.md.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
