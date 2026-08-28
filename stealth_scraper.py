#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stealth_scraper.py
=====================================================================
Anti-bot-hardened headless scraper built on Playwright.

Purpose
-------
Fetching pages that aggressively fingerprint automated browsers can return
"trimmed" HTML (no phone numbers) or a block/CAPTCHA page. This module
hardens a Playwright Chromium crawl in four explicit ways:

  1. STALKER-STEALTH MASKING
     - Applies `playwright-stealth` (playwright_stealth.stealth_sync) which
       neutralises the tell-tale automated-browser fingerprints:
         * navigator.webdriver  -> false (removed/undefined)
         * navigator.plugins, navigator.languages, chrome runtime/permissions
         * missing WebGL / missing browser APIs
       We also inject a belt-and-braces init-script that forces
       navigator.webdriver to undefined for the lifetime of every page.

  2. PER-REQUEST USER-AGENT ROTATION
     - A fresh browser *context* is created for EVERY request.
     - Each context gets a randomly chosen REAL modern UA (mobile or desktop)
       matched to a real viewport, locale, timezone and touch capability.
     - Rotation therefore produces a different fingerprint per request and
       clears cookies/state between requests (matching how search engines
       expect a normal visitor to behave).

  3. RANDOMISED VIEWPORTS + HUMAN-LIKE DELAYS
     - Common real screen sizes are randomised per request.
     - A random 2-5 s sleep (configurable) runs before/after page load,
       plus small random mouse-move / scroll jitter to look human.

  4. EXPLICIT BLOCK / CAPTCHA DETECTION
     - If the response looks like a CAPTCHA, Cloudflare challenge, 403/429,
       "unusual traffic" or a suspiciously thin page, we LOG it in plain text
       instead of returning an empty result silently. Numbers are only
       reported as "missing" together with the actual reason.

Phone numbers are then extracted from the rendered HTML with a tolerant
regex (international + local Kenyan formats) and de-duplicated.

Install:
    pip install playwright playwright-stealth
    playwright install chromium

Usage examples
--------------
    # Scrape one page, printing the result dict:
    python stealth_scraper.py "https://example.com/find/restaurants"
    python stealth_scraper.py "https://example.com/place/nairobi" --urls-file targets.txt --max 20

    # From your own code:
    from stealth_scraper import StealthScraper
    with StealthScraper(headless=True, min_delay=2.0, max_delay=5.0) as s:
        r = s.fetch("https://example.com/search")
        print(r["status"], r["blocked"], r["reason"], r["phones"])
"""

from __future__ import annotations

import argparse
import html
import logging
import random
import re
import time
from typing import List, Optional
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

# =====================================================================
# LOGGING
# =====================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("stealth_scraper")


# =====================================================================
# REAL, MODERN USER-AGENT POOL (mobile + desktop)
# ---------------------------------------------------------------------
# A curated static pool so the script works with zero network lookups.
# (Optionally merged with `fake-useragent` — see load_user_agents().)
# =====================================================================
DESKTOP_UA_POOL = [
    # Chrome / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    # Chrome / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    # Edge / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.2592.87",
    # Firefox / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    # Firefox / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:127.0) Gecko/20100101 Firefox/127.0",
    # Safari / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    # Chrome / Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]

MOBILE_UA_POOL = [
    # Android / Chrome (Pixel 8)
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.6478.122 Mobile Safari/537.36",
    # Android / Chrome (Samsung Galaxy S23 Ultra)
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
    # Android / Samsung Internet
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/25.0 Chrome/125.0.0.0 Mobile Safari/537.36",
    # iPhone / Safari
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    # iPad / Safari
    "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    # Android / Chrome (generic)
    "Mozilla/5.0 (Linux; Android 13; M2007J20CG) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    # Android / Firefox
    "Mozilla/5.0 (Android 14; Mobile; rv:127.0) Gecko/127.0 Firefox/127.0",
]

# Single combined pool used by the loader and CLI
ALL_UA_POOL = DESKTOP_UA_POOL + MOBILE_UA_POOL


# =====================================================================
# VIEWPORT POOLS (match device class)
# =====================================================================
DESKTOP_VIEWPORTS = [
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
    {"width": 1280, "height": 800},
    {"width": 1600, "height": 900},
]

MOBILE_VIEWPORTS = [
    {"width": 375, "height": 812},    # iPhone X/12/13
    {"width": 390, "height": 844},    # iPhone 12/13/14/15
    {"width": 393, "height": 852},    # iPhone 15 Pro
    {"width": 360, "height": 800},    # common Android
    {"width": 412, "height": 915},    # Pixel 7 / Galaxy A
    {"width": 430, "height": 932},    # iPhone 14/15 Pro Max
]

# =====================================================================
# BLOCK / CAPTCHA DETECTION
# =====================================================================
# (regex pattern, human-readable label). Any match => flagged & logged.
BLOCK_INDICATORS = [
    (r"captcha", "generic-CAPTCHA"),
    (r"\brecaptcha\b", "reCAPTCHA"),
    (r"\bhcaptcha\b", "hCaptcha"),
    (r"[Uu]nusual traffic from your computer network", "Google-block"),
    (r"[Vv]erify (that )?you are( a)? human", "human-verification"),
    (r"[Aa]ccess (is )?denied", "access-denied"),
    (r"Attention Required![\s\S]{0,40}Cloudflare", "cloudflare-block"),
    (r"[Cc]hecking your browser", "cloudflare-JS-challenge"),
    (r"[Jj]ust a moment", "cloudflare-JS-challenge"),
    (r"cf-chl-challenge|cf_clearance", "cloudflare-challenge"),
    (r"sorry, you have been blocked", "blocked"),
    (r"API rate limit exceeded", "rate-limited"),
]

# HTTP status codes that most often indicate blocking / throttling.
BLOCK_STATUS_CODES = {401, 403, 404, 429, 503}

# =====================================================================
# PHONE-EXTRACTION (loose + library-validated)
# =====================================================================
# The default region code used for parsing local numbers.
# Kenya is the default; change this one constant to target another country.
DEFAULT_REGION = "KE"

# LOOSE, GREEDY regex: grabs a maximal candidate run that may contain spaces,
# dashes, parentheses, dots and/or a leading plus sign. It does NOT enforce a
# specific format itself — it just captures candidate text (the digit-count
# filter in extract_phones enforces the 7-15 digit rule) and lets the
# `phonenumbers` library decide whether it is a real line.
#   matches:  0712 345678   |   +254712345678   |   0712-345-678
#             0712 345 678  |   (0712) 345678   |   +254 712 345678
LOOSE_PHONE_RE = re.compile(
    r"\+?[\d(][\d\s\-().]{6,}[\d)]"
)

# =====================================================================
# MULTI-SOURCE FALLBACK SETTINGS
# =====================================================================
# DuckDuckGo's lightweight HTML endpoint — no API key, returns server-side
# HTML result snippets we can parse without a page-side JS render.
DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"

# Sequential fallback sources, in priority order:
#   source-key : (query template, description)
# Each is a DuckDuckGo HTML search strung together from the restaurant name +
# neighbourhood. We do NOT deep-dive every directory's internal pages here —
# search-result snippets frequently carry the very phone number we need.
FALLBACK_SOURCES = [
    ("facebook", "{name} {loc} Facebook", "Facebook web result"),
    ("yellow-pages", "{name} {loc} Yellow Pages", "Local business directory"),
    ("delivery", "{name} {loc} Bolt Food OR Uber Eats OR Jumia Food", "Food-delivery listing"),
]


# =====================================================================
# HELPER: USER-AGENT LOADING (optional live pool via fake-useragent)
# =====================================================================
def load_user_agents() -> List[str]:
    """Return the bundled UA pool, optionally augmented with fake-useragent.

    If `fake-useragent` is installed we merge its fresh pool in. Otherwise we
    silently fall back to the bundled real strings (no network calls).
    """
    pool = list(ALL_UA_POOL)
    try:
        from fake_useragent import UserAgent  # type: ignore

        ua = UserAgent(browsers=["chrome", "firefox", "safari", "edge"])
        for _ in range(25):
            try:
                candidate = ua.random
                if candidate and not candidate.startswith("python"):
                    pool.append(candidate)
            except Exception:
                break
        logger.debug("Merged fake-useragent pool -> %d total UAs", len(pool))
    except Exception:
        logger.debug("fake-useragent not installed; using bundled pool (%d UAs)", len(pool))
    return pool


# =====================================================================
# THE SCRAPER
# =====================================================================
class StealthScraper:
    """A hardened, headless Playwright fetcher with stealth & per-request rotation."""

    def __init__(
        self,
        headless: bool = True,
        min_delay: float = 2.0,
        max_delay: float = 5.0,
        mobile_probability: float = 0.5,
        user_agents: Optional[List[str]] = None,
        viewport_jitter: int = 40,
        timeout_ms: int = 45000,
    ) -> None:
        """
        Args:
            headless:            Run Chromium without a visible window.
            min_delay/max_delay: Random sleep bounds (seconds) between actions.
            mobile_probability:  Chance that any single request pretends to be a phone.
            user_agents:         Optional custom UA pool (default: merged real pool).
            viewport_jitter:     +/- px added to chosen viewport for extra realism.
            timeout_ms:          Per-navigation timeout.
        """
        self.headless = headless
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.mobile_probability = mobile_probability
        self.timeout_ms = timeout_ms
        self.viewport_jitter = viewport_jitter
        self.user_agents = user_agents or load_user_agents()
        self._playwright = None
        self._browser = None

    # -- context manager ---------------------------------------------------
    def __enter__(self) -> "StealthScraper":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def start(self) -> None:
        """Launch a persistent Chromium instance (contexts are created per-request)."""
        if self._browser:
            return
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
            )
            logger.info(
                "Browser launched (headless=%s). UA pool size=%d",
                self.headless,
                len(self.user_agents),
            )
        except Exception as exc:  # pragma: no cover - practical only if deps missing
            logger.error(
                "Could not launch Chromium: %s\n   Did you run:  playwright install chromium ?",
                exc,
            )
            raise

    def close(self) -> None:
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
        logger.info("Browser closed.")

    # -- randomness helpers ------------------------------------------------
    def _random_ua(self, is_mobile: bool) -> str:
        if is_mobile:
            pool = [u for u in self.user_agents if ("Mobile" in u or "Android" in u)]
        else:
            pool = [u for u in self.user_agents if ("Mobile" not in u)]
        pool = pool or self.user_agents
        return random.choice(pool)

    def _random_viewport(self, is_mobile: bool) -> dict:
        base = random.choice(MOBILE_VIEWPORTS if is_mobile else DESKTOP_VIEWPORTS)
        jitter = self.viewport_jitter
        width = max(320, base["width"] + random.randint(-jitter, jitter))
        height = max(480, base["height"] + random.randint(-jitter, jitter))
        return {"width": width, "height": height}

    def _random_locale(self) -> str:
        return random.choice(["en-US", "en", "en-GB"])

    def _sleep(self, extra: float = 0.0) -> None:
        """Random human-like sleep between actions (default 2-5 s)."""
        delay = random.uniform(self.min_delay, self.max_delay)
        if extra:
            delay += extra
        time.sleep(delay)

    def _human_jitter(self, page) -> None:
        """Small, realistic mouse & scroll wiggle so behaviour isn't perfectly linear."""
        try:
            if random.random() < 0.4:
                page.mouse.move(
                    random.randint(30, 160),
                    random.randint(30, 140),
                    steps=random.randint(3, 8),
                )
                time.sleep(random.uniform(0.1, 0.4))
            if random.random() < 0.3:
                page.mouse.wheel(0, random.randint(80, 320))
                time.sleep(random.uniform(0.1, 0.5))
        except Exception:
            pass  # non-critical; never break the fetch because of jitter

    # -- block / captcha detection -----------------------------------------
    @staticmethod
    def detect_block(status: Optional[int], html_text: str) -> Optional[str]:
        """Return a human-readable block reason, or None if the page looks fine."""
        if status in BLOCK_STATUS_CODES:
            return f"HTTP-{status}"
        body = re.sub(r"<[^>]+>", " ", html_text)  # strip markup before matching
        for pattern, label in BLOCK_INDICATORS:
            if re.search(pattern, body, flags=re.IGNORECASE):
                return label
        # Heuristic: a "results"/detail page that is suspiciously tiny usually
        # means the server returned a generic/shell template with no real data.
        if len(html_text) < 400:
            return "thin-or-empty-page"
        return None

    # -- phone extraction --------------------------------------------------
    @staticmethod
    def extract_phones(html_text: str) -> List[str]:
        """Extract phone numbers from raw HTML using loose capture + the
        `phonenumbers` library for authoritative validation.

        Each unreasonably-formatted candidate captured by LOOSE_PHONE_RE is
        passed straight into `phonenumbers.parse(text, DEFAULT_REGION)`, then
        kept only if BOTH `is_possible_number()` and `is_valid_number()` pass.
        This catches 0712 345678 / +254712345678 / 0712-345-678 / (0712) 345678
        and any other local formatting that a strict regex would miss.
        Returns normalized E.164 strings, de-duplicated, in order of first hit.
        """
        # Import lazily so the rest of the module loads even if the optional
        # dependency isn't installed yet.
        try:
            import phonenumbers  # noqa: PLC0415
        except ImportError:
            logger.error(
                "phonenumbers is required for validation. Install with: "
                "pip install phonenumbers"
            )
            return []

        # Strip markup + decode HTML entities so we only match visible text,
        # never hidden attributes.
        plain = html.unescape(re.sub(r"<[^>]+>", " ", html_text))

        seen: set = set()
        numbers: List[str] = []

        for match in LOOSE_PHONE_RE.finditer(plain):
            raw = match.group(0).strip(" ,;:()\t\r\n")

            # Enforce the 7-15 digit rule on the captured run (the loose regex
            # is intentionally minimal; the digit count IS the filter here).
            digit_count = sum(ch.isdigit() for ch in raw)
            if digit_count < 7 or digit_count > 15:
                continue

            # Let the library (not a strict regex) decide if it's a real line.
            try:
                number = phonenumbers.parse(raw, DEFAULT_REGION)
            except phonenumbers.NumberParseException:
                continue  # unparsable -> skip silently, it is not a phone

            if not (
                phonenumbers.is_possible_number(number)
                and phonenumbers.is_valid_number(number)
            ):
                continue

            e164 = phonenumbers.format_number(
                number, phonenumbers.PhoneNumberFormat.E164
            )
            if e164 not in seen:
                seen.add(e164)
                numbers.append(e164)

        return numbers

    # -- main fetch --------------------------------------------------------
    def fetch(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        max_wait_ms: Optional[int] = None,
    ) -> dict:
        """
        Fetch a single URL with a fresh, random fingerprint and return:
            {url, status, blocked, reason, phones, html_len}
        """
        timeout = max_wait_ms if max_wait_ms is not None else self.timeout_ms

        # 1) Random fingerprint for THIS request.
        is_mobile = random.random() < self.mobile_probability
        user_agent = self._random_ua(is_mobile)
        viewport = self._random_viewport(is_mobile)
        locale = self._random_locale()

        # 2) Isolated context per request -> UA rotation + no cookie carry-over.
        context = self._browser.new_context(
            user_agent=user_agent,
            viewport=viewport,
            locale=locale,
            timezone_id="Africa/Nairobi",
            is_mobile=is_mobile,
            has_touch=is_mobile,
            device_scale_factor=1 if not is_mobile else 2,
            color_scheme="light",
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

        result = {
            "url": url,
            "status": None,
            "blocked": False,
            "reason": None,
            "phones": [],
            "html_len": 0,
            "html_text": "",
        }

        page = None
        try:
            page = context.new_page()

            # 1) Stealth masking (playwright-stealth).
            stealth_sync(page)
            # Belt-and-braces: force navigator.webdriver to undefined.
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )

            # 3) Human-like delay BEFORE interacting (respect robots etiquette).
            self._sleep()

            # 4) Navigate.
            response = page.goto(url, wait_until=wait_until, timeout=timeout)

            # 3) Random human delay + jitter after load, before reading content.
            self._sleep(extra=random.uniform(0, 1.0))
            self._human_jitter(page)

            status = response.status if response else None
            html_text = page.content()
            result["html_text"] = html_text

            reason = self.detect_block(status, html_text)
            result["status"] = status
            result["html_len"] = len(html_text)

            if reason:
                result["blocked"] = True
                result["reason"] = reason
                logger.warning(
                    "[%s] BLOCK/CAPTCHA detected (status=%s, reason=%s). html_len=%d",
                    url, status, reason, len(html_text),
                )
            else:
                phones = self.extract_phones(html_text)
                result["phones"] = phones
                logger.info(
                    "[%s] OK status=%s phones=%d html_len=%d",
                    url, status, len(phones), len(html_text),
                )
            return result

        except Exception as exc:  # noqa: BLE001 - surface the real cause, don't fail silently
            result["blocked"] = True
            result["reason"] = f"UNKNOWN-ERROR: {type(exc).__name__}: {exc}"
            logger.error("[%s] Fetch raised %s: %s", url, type(exc).__name__, exc)
            return result
        finally:
            if page is not None:
                try:
                    context.close()  # frees the fresh fingerprint
                except Exception:
                    pass

    # =====================================================================
    # MULTI-SOURCE FALLBACK (DuckDuckGo HTML search pipeline)
    # =====================================================================
    @staticmethod
    def _strip_tags(text: str) -> str:
        """Remove HTML tags, decode entities and collapse whitespace."""
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _extract_snippets(html_text: str) -> List[str]:
        """Pull the visible result snippets out of a DuckDuckGo HTML page.

        The lightweight `html.duckduckgo.com` endpoint renders each result's
        snippet inside `<a class="result__snippet">...</a>`. We collect those
        text blocks so we can hunt for phone numbers inside search results
        (not just the page the results link to).
        """
        texts: List[str] = []
        # Primary layout: snippet is an <a> with class containing result__snippet.
        pat = re.compile(
            r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        for m in pat.finditer(html_text):
            t = StealthScraper._strip_tags(m.group(1))
            if t:
                texts.append(t)
        # Fallback layout: some mirrors wrap the snippet in a <div> instead.
        if not texts:
            pat_div = re.compile(
                r'<div[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>',
                re.IGNORECASE | re.DOTALL,
            )
            for m in pat_div.finditer(html_text):
                t = StealthScraper._strip_tags(m.group(1))
                if t:
                    texts.append(t)
        return texts

    def _ddg_search(self, query: str) -> List[str]:
        """Run one DuckDuckGo HTML search and return the snippet texts.

        Uses the same stealth + rotation + human-delay + block-detection path
        as every other request, so a blocked/CAPTCHA reply is logged, not
        silently swallowed.
        """
        url = f"{DUCKDUCKGO_HTML_URL}?{urlencode({'q': query})}"
        res = self.fetch(url)
        if res["blocked"]:
            logger.warning(
                "[fallback] DuckDuckGo blocked for query %r (reason=%s); moving on.",
                query,
                res["reason"],
            )
            return []
        snippets = self._extract_snippets(res["html_text"])
        if not snippets:
            logger.info("[fallback] No snippets parsed for query %r.", query)
        return snippets

    @staticmethod
    def _choose_best(all_numbers: List[str], source_map) -> Optional[str]:
        """Pick the most credible number from the merged pool.

        Scoring (best wins):
            1. appears in the most distinct fallback SOURCES (more independent
               evidence => more likely a live, active line), then
            2. appears earliest in discovery order (stable tie-break).
        Every number here already passed phonenumbers validity checks.
        """
        if not all_numbers:
            return None
        return max(all_numbers, key=lambda n: len(source_map[n]))

    def fallback_search(
        self,
        name: str,
        neighborhood: str = "",
        primary_phone: Optional[str] = None,
        force: bool = False,
    ) -> dict:
        """Sequential multi-source fallback when the primary phone is missing.

        Sources (in order): Facebook web results -> Yellow Pages/local
        directories -> food-delivery indexes (Bolt Food / Uber Eats /
        Jumia Food). Every number found is merged, de-duplicated, and the most
        credible one is returned for updating the database.

        Returns:
            {
              "primary":     primary_phone (as passed in),
              "best_number": chosen phone, or the primary if nothing new found,
              "all_numbers": unique valid E.164 numbers from the fallback,
              "sources":     per-source record of results,
            }
        """
        if primary_phone and not force:
            logger.info(
                "[fallback] Primary phone present (%s); skipping multi-source fallback.",
                primary_phone,
            )
            return {
                "primary": primary_phone,
                "best_number": primary_phone,
                "all_numbers": [],
                "sources": [],
            }

        base = (name or "").strip()
        loc = (neighborhood or "").strip()
        if not base:
            logger.warning("[fallback] No restaurant name given; nothing to search for.")
            return {
                "primary": primary_phone,
                "best_number": primary_phone,
                "all_numbers": [],
                "sources": [],
            }

        source_map: dict = {}     # E.164 -> set(source keys) for evidence
        order: List[str] = []     # discovery order (de-dup key / stable tie-break)
        sources: List[dict] = []

        for source_key, template, desc in FALLBACK_SOURCES:
            query = template.format(name=base, loc=loc).strip()

            # Sequential + human-paced between sources (respect rate limits).
            self._sleep()

            snippets = self._ddg_search(query)
            numbers: List[str] = []

            for snippet in snippets:
                for e164 in self.extract_phones(snippet):
                    if e164 not in source_map:
                        source_map[e164] = set()
                        order.append(e164)
                    source_map[e164].add(source_key)
                    if e164 not in numbers:
                        numbers.append(e164)

            sources.append({
                "source": source_key,
                "description": desc,
                "query": query,
                "numbers": numbers,
            })

            if numbers:
                logger.info(
                    "[fallback] %s found %d number(s): %s",
                    source_key, len(numbers), numbers,
                )
            else:
                logger.info("[fallback] %s yielded no phone numbers.", source_key)

        all_numbers = list(order)  # unique, first-seen order
        best = self._choose_best(order, source_map) if order else (primary_phone or None)

        logger.info(
            "[fallback] Merged %d unique number(s); best choice = %s",
            len(all_numbers), best,
        )

        return {
            "primary": primary_phone,
            "best_number": best,
            "all_numbers": all_numbers,
            "sources": sources,
        }


# =====================================================================
# CLI (run standalone)
# =====================================================================
def _read_urls(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip() and not line.startswith("#")]


def main() -> None:
    parser = argparse.ArgumentParser(description="Stealth Playwright phone-number scraper")
    parser.add_argument("url", nargs="?", help="A single URL to scrape")
    parser.add_argument("--urls-file", "-f", help="File with one URL per line (# = comment)")
    parser.add_argument("--max", type=int, default=25, help="Cap number of URLs to fetch")
    parser.add_argument("--visible", action="store_true", help="Run headed (not headless)")
    parser.add_argument("--min-delay", type=float, default=2.0, help="Min human delay seconds")
    parser.add_argument("--max-delay", type=float, default=5.0, help="Max human delay seconds")
    args = parser.parse_args()

    urls: List[str] = []
    if args.urls_file:
        urls = _read_urls(args.urls_file)[: args.max]
    elif args.url:
        urls = [args.url]
    else:
        parser.error("Pass a URL or --urls-file FILE")

    logger.info("Scraping %d URL(s) ...", len(urls))

    with StealthScraper(
        headless=not args.visible, min_delay=args.min_delay, max_delay=args.max_delay
    ) as scraper:
        for url in urls:
            r = scraper.fetch(url)
            summary = (
                f"status={r['status']} "
                f"blocked={r['blocked']}"
                + (f" ({r['reason']})" if r["blocked"] else "")
                + f" phones={r['phones'] or 'NONE'}"
            )
            print(f"{url}\n  -> {summary}")


if __name__ == "__main__":
    main()