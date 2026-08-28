#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_assets.py
=====================================================================
Generates the site's brand image assets used for SEO / social sharing
and the PWA manifest. Run it whenever branding changes:

    python generate_assets.py

Outputs (written into static/):
  - og-image.png         1200x630  social share preview (og:image / twitter:image)
  - apple-touch-icon.png  180x180  iOS home-screen icon
  - icon-192.png          192x192  manifest icon
  - icon-512.png          512x512  manifest icon

The look matches the app's sidebar gradient (#667eea -> #764ba2).
Emoji rendering uses Segoe UI Emoji when available and silently falls back
to a drawn plate/fork motif if the colour font cannot be used, so the script
works on any machine.
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "static")

# Brand colours (same gradient as the sidebar in style.css)
GRAD_START = (102, 126, 234)   # #667eea
GRAD_END = (118, 75, 162)      # #764ba2
WHITE = (255, 255, 255, 255)
SOFT_WHITE = (255, 255, 255, 215)

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\segoeuib.ttf",   # Segoe UI Bold
    r"C:\Windows\Fonts\segoeui.ttf",    # Segoe UI
    r"C:\Windows\Fonts\arialbd.ttf",    # Arial Bold
    r"C:\Windows\Fonts\arial.ttf",      # Arial
]
EMOJI_CANDIDATES = [
    r"C:\Windows\Fonts\seguiemj.ttf",   # Segoe UI Emoji (colour)
]
# Pillow requires this exact size for colour COLR/CPAL emoji fonts.
EMOJI_FONT_SIZE = 109


def _first_font(candidates):
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def draw_gradient(size, horizontal_bias=1.35):
    """Return an RGBA image with the brand diagonal gradient."""
    w, h = size
    img = Image.new("RGBA", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            # Diagonal gradient (x weighted more, like CSS 135deg).
            t = (x / max(1, w - 1) * horizontal_bias + y / max(1, h - 1)) / (1 + horizontal_bias)
            t = min(1.0, max(0.0, t))
            r = int(GRAD_START[0] + (GRAD_END[0] - GRAD_START[0]) * t)
            g = int(GRAD_START[1] + (GRAD_END[1] - GRAD_START[1]) * t)
            b = int(GRAD_START[2] + (GRAD_END[2] - GRAD_START[2]) * t)
            px[x, y] = (r, g, b, 255)
    return img


def _paste_emoji(draw_img, emoji_char, box_center, target_size):
    """Try to paste a colour emoji centred in box_center. Returns True on success."""
    emoji_path = _first_font(EMOJI_CANDIDATES)
    if not emoji_path:
        return False
    try:
        font = ImageFont.truetype(emoji_path, EMOJI_FONT_SIZE)
        tmp = Image.new("RGBA", (EMOJI_FONT_SIZE * 2, EMOJI_FONT_SIZE * 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(tmp)
        d.text((EMOJI_FONT_SIZE // 2, EMOJI_FONT_SIZE // 4), emoji_char,
               font=font, embedded_color=True, fill=WHITE)
        bbox = tmp.getbbox()
        if not bbox:
            return False
        glyph = tmp.crop(bbox)
        glyph.thumbnail((target_size, target_size), Image.LANCZOS)
        cx, cy = box_center
        draw_img.alpha_composite(
            glyph, (int(cx - glyph.width / 2), int(cy - glyph.height / 2))
        )
        return True
    except Exception:
        return False


def _draw_plate_fallback(draw_img, box_center, radius):
    """Simple plate + fork/knife motif used when colour emoji is unavailable."""
    cx, cy = box_center
    draw_img.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                     outline=WHITE, width=max(4, radius // 14))
    inner = int(radius * 0.68)
    draw_img.ellipse([cx - inner, cy - inner, cx + inner, cy + inner],
                     outline=SOFT_WHITE, width=max(2, radius // 22))
    # Fork (left) and knife (right) as simple strokes.
    for sign in (-1, 1):
        x = cx + sign * int(radius * 1.45)
        draw_img.line([x, cy - int(radius * 0.55), x, cy + int(radius * 0.55)],
                      fill=WHITE, width=max(4, radius // 16))


def _fit_font(path, text, start_size, max_width):
    """Return a font whose rendered width fits within max_width."""
    size = start_size
    while size > 12:
        font = ImageFont.truetype(path, size)
        if ImageDraw.Draw(Image.new("RGB", (10, 10))).textlength(text, font=font) <= max_width:
            return font
        size -= 2
    return ImageFont.truetype(path, size)


def make_icon(size, emoji_char="🍽️", use_emoji=True):
    """Build the app icon at the requested size (rounded corners)."""
    img = draw_gradient((size, size), horizontal_bias=1.0)
    mask = Image.new("L", (size, size), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.18), fill=255)
    img.putalpha(mask)

    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    radius = int(size * 0.30)
    if not (use_emoji and _paste_emoji(layer, emoji_char, (size / 2, size / 2), radius)):
        _draw_plate_fallback(d, (size / 2, size / 2), radius)
    img.alpha_composite(layer)
    return img


def _load_fonts():
    path = _first_font(FONT_CANDIDATES)
    if not path:
        return ImageFont.load_default(), ImageFont.load_default(), ImageFont.load_default()
    return (
        ImageFont.truetype(path, 74),
        ImageFont.truetype(path, 32),
        ImageFont.truetype(path, 26),
    )


def make_og_image(emoji_char="🍽️"):
    """Build the 1200x630 social share preview."""
    w, h = 1200, 630
    img = draw_gradient((w, h))
    title_font, sub_font, badge_font = _load_fonts()
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    # Icon badge on the left (drawn on the overlay so its translucent
    # fill actually blends instead of replacing pixels with solid white).
    badge_r = 92
    bx, by = 150, int(h / 2) - 30
    od.ellipse([bx - badge_r, by - badge_r, bx + badge_r, by + badge_r],
               fill=(255, 255, 255, 40), outline=(255, 255, 255, 95), width=3)
    if not _paste_emoji(overlay, emoji_char, (bx, by), int(badge_r * 1.12)):
        _draw_plate_fallback(ImageDraw.Draw(overlay), (bx, by), int(badge_r * 0.62))
    img.alpha_composite(overlay)
    d = ImageDraw.Draw(img)

    # Text block to the right of the badge.
    tx = 290
    max_text_w = w - tx - 30   # keep text inside the right margin

    line1 = "Kenya Restaurant"
    line2 = "Finder"
    sub1 = "Live map of restaurants in Kenya without a website."
    sub2 = "Phone & WhatsApp contacts, county search, Excel export."

    d.text((tx, int(h * 0.24)), line1, font=title_font, fill=WHITE)
    d.text((tx, int(h * 0.24) + 88), line2, font=title_font, fill=WHITE)

    sub1_font = _fit_font(_first_font(FONT_CANDIDATES) or "arial.ttf",
                          sub1, 32, max_text_w)
    sub2_font = _fit_font(_first_font(FONT_CANDIDATES) or "arial.ttf",
                          sub2, 32, max_text_w)
    d.text((tx, int(h * 0.24) + 196), sub1, font=sub1_font, fill=SOFT_WHITE)
    d.text((tx, int(h * 0.24) + 248), sub2, font=sub2_font, fill=SOFT_WHITE)

    # Small badge at the bottom (also on the overlay so it stays translucent).
    od = ImageDraw.Draw(overlay)
    badge_w, badge_h = 340, 52
    badge_y = int(h * 0.82)
    od.rounded_rectangle([tx, badge_y, tx + badge_w, badge_y + badge_h],
                         radius=26, fill=(255, 255, 255, 40),
                         outline=(255, 255, 255, 90), width=2)
    img.alpha_composite(overlay)
    d = ImageDraw.Draw(img)
    d.text((tx + 26, badge_y + 12), "Leaflet + OpenStreetMap",
           font=badge_font, fill=WHITE)

    return img.convert("RGB")


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    targets = {
        "og-image.png": ("og", None),
        "apple-touch-icon.png": ("icon", 180),
        "icon-192.png": ("icon", 192),
        "icon-512.png": ("icon", 512),
    }

    for name, (kind, size) in targets.items():
        path = os.path.join(OUT_DIR, name)
        if kind == "og":
            img = make_og_image()
        else:
            img = make_icon(size)
        img.save(path, format="PNG", optimize=True)
        print(f"wrote {name}  {img.size[0]}x{img.size[1]}")

    print("done.")


if __name__ == "__main__":
    main()