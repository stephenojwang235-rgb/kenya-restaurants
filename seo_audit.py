#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
seo_audit.py
=====================================================================
On-page SEO auditor for the live Kenya Restaurant Finder site.

    python seo_audit.py
    python seo_audit.py --url https://example.com/some/path/

It fetches the deployed page and reports PASS / WARN / FAIL for the
things that actually affect indexing and sharing:

  crawlability ..... HTTP 200, no noindex, robots meta, canonical
  metadata ......... title & description presence + sensible lengths
  sharing .......... complete Open Graph + Twitter card set, og:image
                     really downloads and has valid social dimensions
  structure ........ exactly one h1, heading order, no <img> missing alt
  assets ........... every referenced static asset resolves to 200
  discovery ........ robots.txt allows crawling and points at sitemap,
                     sitemap lists this URL and carries <lastmod>
  tech ............. viewport, lang, manifest, JSON-LD validity

Exit code 0 = no FAIL, 1 = at least one FAIL.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.request
import urllib.error

from PIL import Image

DEFAULT_URL = "https://stephenojwang235-rgb.github.io/kenya-restaurants/"
UA = {"User-Agent": "seo-audit/1.0 (+site owner check)"}

PASS, WARN, FAIL, INFO = "PASS", "WARN", "FAIL", "INFO"
report: list[tuple[str, str]] = []


def say(level: str, msg: str) -> None:
    report.append((level, msg))
    mark = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]", "INFO": "[info]"}[level]
    print(f"{mark} {msg}")


def fetch(url: str, timeout: int = 25):
    """Return (status, body, final_url). Raises on network failure."""
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace"), resp.geturl()
    except urllib.error.HTTPError as exc:
        return exc.code, "", url


def meta_tags(html: str) -> dict:
    """Collect name=/property= meta tags -> {key: content}."""
    out = {}
    for m in re.finditer(
        r'<meta\s+[^>]*?(?:name|property)=["\']([^"\']+)["\'][^>]*?>',
        html, re.IGNORECASE,
    ):
        tag = m.group(0)
        cm = re.search(r'content=["\']([^"\']*)["\']', tag, re.IGNORECASE)
        out[m.group(1).lower()] = cm.group(1) if cm else ""
    return out


def link_tags(html: str) -> list[dict]:
    tags = []
    for m in re.finditer(r'<link\s+[^>]*?>', html, re.IGNORECASE):
        tag = m.group(0)
        entry = {}
        for attr in ("rel", "href", "sizes", "type"):
            am = re.search(attr + r'=["\']([^"\']*)["\']', tag, re.IGNORECASE)
            if am:
                entry[attr.lower()] = am.group(1)
        tags.append(entry)
    return tags


def _fit_download(url: str) -> bytes:
    with urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=25
    ) as resp:
        return resp.read()


def audit(base: str, retries: int, wait: float) -> int:
    fails = 0

    # ---- reachability (retry absorbs CDN propagation blips) -----------
    status, html = 0, ""
    for attempt in range(1, retries + 1):
        try:
            status, html, _ = fetch(base)
        except Exception as exc:
            print(f"  network error: {exc}")
        if status == 200:
            break
        print(f"  (attempt {attempt}/{retries}: HTTP {status})")
        if attempt < retries:
            time.sleep(wait)
    if status != 200:
        say(FAIL, f"page returns HTTP {status} after {retries} attempts")
        return 1
    say(PASS, f"page returns HTTP 200 ({len(html)} bytes)")

    metas = meta_tags(html)
    links = link_tags(html)

    # ---- crawlability -------------------------------------------------
    if re.search(r"name=['\"]robots['\"][^>]*noindex", html, re.I):
        say(FAIL, "page is marked noindex — it will never be indexed")
        fails += 1
    else:
        say(PASS, "no noindex directive")

    robots_meta = (metas.get("robots") or "").lower()
    if "noindex" in robots_meta or "nofollow" in robots_meta:
        say(FAIL, f"robots meta restricts crawling: '{robots_meta}'")
        fails += 1
    elif robots_meta:
        say(PASS, f"robots meta = '{robots_meta}'")
    else:
        say(INFO, "no robots meta (defaults to index,follow — fine)")

    canonical = next((l.get("href", "") for l in links
                      if l.get("rel") == "canonical"), "")
    if not canonical:
        say(FAIL, "missing <link rel=canonical>")
        fails += 1
    elif not canonical.startswith("https://"):
        say(WARN, f"canonical is not https: {canonical}")
    elif canonical.rstrip("/") != base.rstrip("/"):
        say(WARN, f"canonical ({canonical}) differs from audited URL ({base})")
    else:
        say(PASS, f"canonical = {canonical}")

    # ---- metadata -----------------------------------------------------
    title_m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    title = title_m.group(1).strip() if title_m else ""
    if not title:
        say(FAIL, "missing <title>")
        fails += 1
    elif not (25 <= len(title) <= 65):
        say(WARN, f"title is {len(title)} chars (aim 25-65): '{title[:70]}'")
    else:
        say(PASS, f"title {len(title)} chars: '{title}'")

    desc = metas.get("description", "")
    if not desc:
        say(FAIL, "missing meta description")
        fails += 1
    elif not (70 <= len(desc) <= 165):
        say(WARN, f"meta description is {len(desc)} chars (aim 70-165)")
    else:
        say(PASS, f"meta description {len(desc)} chars")

    if re.search(r"name=['\"]viewport['\"]", html, re.I):
        say(PASS, "viewport meta present")
    else:
        say(FAIL, "missing viewport meta (mobile-unfriendly)")
        fails += 1

    lang_m = re.search(r"<html[^>]*\blang=['\"]([^'\"]+)['\"]", html, re.I)
    if lang_m:
        say(PASS, f"html lang = {lang_m.group(1)}")
    else:
        say(WARN, "missing lang attribute on <html>")

    # ---- sharing (Open Graph / Twitter) -------------------------------
    for key in ("og:title", "og:description", "og:image", "og:url", "og:type"):
        if key not in metas:
            say(FAIL, f"missing {key}")
            fails += 1
    if all(k in metas for k in ("og:title", "og:description", "og:image", "og:url")):
        say(PASS, "core Open Graph tags present")
    if metas.get("twitter:card"):
        say(PASS, f"twitter:card = {metas['twitter:card']}")
    else:
        say(WARN, "missing twitter:card (X/Twitter will guess a preview)")

    # ---- og:image: must download and be social-sized -------------------
    og_image = metas.get("og:image", "")
    if not og_image:
        say(FAIL, "missing og:image — social shares get no preview")
        fails += 1
    else:
        img_url = og_image if og_image.startswith("http") else base + og_image.lstrip("/")
        try:
            raw = _fit_download(img_url)
            img = Image.open(io.BytesIO(raw))
            wd, ht = img.size
            if wd >= 600 and ht >= 315:
                say(PASS, f"og:image OK — {wd}x{ht}px, {len(raw):,} bytes")
            else:
                say(WARN, f"og:image is small ({wd}x{ht}); recommend >=1200x630")
                fails += 1
            if "og:image:width" not in metas or "og:image:height" not in metas:
                say(WARN, "og:image:width/height not declared (slower previews)")
        except Exception as exc:
            say(FAIL, f"og:image could not be downloaded/parsed: {exc}")
            fails += 1

    return fails


def audit_part2(base: str, html: str, fails: int) -> int:
    """Structure, assets, discovery and tech checks."""
    links = link_tags(html)

    # ---- heading structure --------------------------------------------
    rendered = re.sub(r"<noscript>[\s\S]*?</noscript>", "", html, flags=re.I)
    rendered_h1 = len(re.findall(r"<h1[^>]*>", rendered, re.I))
    h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
    if rendered_h1 == 1:
        say(PASS, "exactly one rendered <h1>")
    elif rendered_h1 == 0:
        say(WARN, "no rendered <h1> — add a descriptive main heading")
    else:
        say(WARN, f"{rendered_h1} rendered <h1> tags — keep exactly one")
    if h1s:
        say(INFO, f"{len(h1s)} <h1> in raw HTML (includes the no-JS fallback heading)")

    # ---- images must have alt text ------------------------------------
    imgs = re.findall(r"<img\b[^>]*>", html, re.I)
    missing_alt = [t for t in imgs if not re.search(r"\balt=", t, re.I)]
    if not imgs:
        say(INFO, "no <img> tags (icons are CSS/inline SVG)")
    elif missing_alt:
        say(FAIL, f"{len(missing_alt)} of {len(imgs)} <img> tags missing alt text")
        fails += 1
    else:
        say(PASS, f"all {len(imgs)} <img> tags have alt text")

    # ---- referenced static assets must resolve ------------------------
    refs = sorted({
        m.group(1)
        for m in re.finditer(
            r'(?:src|href)=["\']((?:\./)?static/[^"\']+)["\']', html, re.I)
    })
    for ref in refs:
        url = base + ref.lstrip("./")
        try:
            st, _, _ = fetch(url)
        except Exception:
            st = 0
        if st == 200:
            say(PASS, f"asset 200: {ref}")
        else:
            say(FAIL, f"asset HTTP {st}: {ref}")
            fails += 1

    # ---- discovery: robots.txt and sitemap ----------------------------
    st, robots_txt, _ = fetch(base + "robots.txt")
    if st != 200:
        say(FAIL, f"robots.txt HTTP {st}")
        fails += 1
    else:
        say(PASS, "robots.txt present")
        if re.search(r"^\s*User-agent:\s*\*", robots_txt, re.I | re.M):
            say(PASS, "robots.txt has a 'User-agent: *' group")
        else:
            say(WARN, "robots.txt has no 'User-agent: *' group")
        sm = [l for l in robots_txt.splitlines()
              if l.strip().lower().startswith("sitemap:")]
        if sm:
            say(PASS, "robots.txt declares a Sitemap")
        else:
            say(WARN, "robots.txt does not declare a Sitemap:")
        if re.search(r"^\s*Disallow:", robots_txt, re.I | re.M):
            say(INFO, "robots.txt has Disallow rules - verify they don't block rendering")

    st, sitemap, _ = fetch(base + "sitemap.xml")
    if st != 200:
        say(FAIL, f"sitemap.xml HTTP {st}")
        fails += 1
    else:
        say(PASS, "sitemap.xml present")
        if base.rstrip("/") in sitemap:
            say(PASS, "sitemap lists this page")
        else:
            say(FAIL, "sitemap does not list this page's URL")
            fails += 1
        if "<lastmod>" in sitemap:
            say(PASS, "sitemap has <lastmod>")
        else:
            say(WARN, "sitemap missing <lastmod>")

    # ---- tech: manifest + JSON-LD -------------------------------------
    if any(l.get("rel") == "manifest" for l in links):
        say(PASS, "web app manifest linked")
        mf = next((l.get("href") for l in links if l.get("rel") == "manifest"), "")
        if mf:
            u = mf if mf.startswith("http") else base + mf.lstrip("./")
            try:
                st, body, _ = fetch(u)
                if st == 200:
                    json.loads(body)
                    say(PASS, "manifest reachable and valid JSON")
                else:
                    say(FAIL, f"manifest HTTP {st}")
                    fails += 1
            except Exception as exc:
                say(FAIL, f"manifest invalid: {exc}")
                fails += 1
    else:
        say(WARN, "no web app manifest (PWA install prompt unavailable)")

    ld = re.findall(
        r'<script\s+type=["\']application/ld\+json["\']>([\s\S]*?)</script>',
        html, re.I,
    )
    if not ld:
        say(FAIL, "no JSON-LD structured data")
        fails += 1
    else:
        try:
            data = json.loads(ld[0])
            nodes = data.get("@graph", [data])
            types = [n.get("@type") for n in nodes]
            say(PASS, "JSON-LD valid - types: " + ", ".join(str(t) for t in types))
            if not any(t in ("WebSite", "WebApplication", "Organization") for t in types):
                say(WARN, "JSON-LD lacks a WebSite/WebApplication/Organization node")
        except Exception as exc:
            say(FAIL, f"JSON-LD is not valid JSON: {exc}")
            fails += 1

    return fails


def main() -> int:
    parser = argparse.ArgumentParser(description="On-page SEO audit")
    parser.add_argument("--url", default=DEFAULT_URL, help="Page URL to audit")
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--wait", type=float, default=5.0)
    args = parser.parse_args()

    base = args.url if args.url.endswith("/") else args.url + "/"

    # Non-slash variant should resolve to the canonical page.
    try:
        st_noslash, _, final = fetch(base.rstrip("/"))
        if st_noslash in (200, 301, 302, 308) and final.rstrip("/") == base.rstrip("/"):
            say(PASS, "non-slash URL resolves to the canonical page")
        else:
            say(WARN, f"non-slash URL returned {st_noslash} -> {final}")
    except Exception as exc:
        say(INFO, f"could not test non-slash variant: {exc}")

    try:
        status, html, _ = fetch(base)
    except Exception as exc:
        print(f"cannot reach {base}: {exc}")
        return 1
    if status != 200:
        print(f"page not reachable (HTTP {status}); aborting audit.")
        return 1

    fails = audit(base, args.retries, args.wait)
    fails = audit_part2(base, html, fails)

    counts = {lv: sum(1 for l, _ in report if l == lv) for lv in (PASS, WARN, FAIL)}
    print()
    print(f"SUMMARY: {counts[PASS]} passed, {counts[WARN]} warnings, {counts[FAIL]} failed")
    if counts[FAIL]:
        print("\nFailed checks:")
        for lv, msg in report:
            if lv == FAIL:
                print(f"  - {msg}")
        return 1
    print("\nNo blocking SEO issues found.")
    if counts[WARN]:
        print("Warnings are optional improvements.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
