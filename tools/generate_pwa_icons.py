"""Generate Terra Nova PWA icons with Pillow.

Run from the project root:

    env/bin/python tools/generate_pwa_icons.py

Outputs (into static/img/pwa/):
    icon-192x192.png            any-purpose icon
    icon-512x512.png            any-purpose icon (install prompt)
    maskable-512x512.png        maskable icon (Android adaptive, full-bleed)
    apple-touch-icon-180x180.png  iOS home screen icon (opaque)
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT_DIR = Path(__file__).resolve().parents[1] / 'static' / 'img' / 'pwa'
SS = 4  # supersampling factor — icons are drawn at 4x then downscaled

OCEAN_TOP = (74, 148, 218)
OCEAN_BOTTOM = (10, 42, 84)
LAND_COLORS = [(46, 125, 90), (53, 110, 74), (134, 119, 75)]
GLOW = (90, 168, 255)
VOID_RGB = (4, 6, 11)

# Landmass blobs as (x1, y1, x2, y2) fractions of the planet radius
BLOBS = [
    (-0.58, -0.32, -0.05, 0.16),
    (-0.24, 0.32, 0.26, 0.64),
    (0.12, -0.52, 0.62, -0.08),
    (0.34, 0.08, 0.72, 0.52),
    (-0.12, -0.08, 0.2, 0.22),
    (0.52, -0.64, 0.88, -0.34),
]


def vertical_gradient(size, top, bottom):
    strip = Image.new('RGB', (1, 256))
    px = strip.load()
    for y in range(256):
        t = y / 255
        px[0, y] = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return strip.resize((size, size), Image.BILINEAR)


def diagonal_ramp(size, start, end):
    """Alpha ramp from top-left to bottom-right (small image, upscaled)."""
    low = 128
    img = Image.new('L', (low, low))
    px = img.load()
    for y in range(low):
        for x in range(low):
            t = (x + y) / (2 * (low - 1))
            px[x, y] = round(start + (end - start) * t)
    return img.resize((size, size), Image.BILINEAR)


def build_icon(n, *, bg=None, ratio=0.8, glow=True):
    size = n * SS
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    if bg:
        canvas.paste(Image.new('RGBA', (size, size), bg + (255,)), (0, 0))

    cx = cy = size // 2
    r = int(size * ratio / 2)

    # Atmosphere glow behind the planet
    if glow:
        halo = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        pad = size * 0.05
        ImageDraw.Draw(halo).ellipse(
            [cx - r - pad, cy - r - pad, cx + r + pad, cy + r + pad],
            fill=GLOW + (115,),
        )
        halo = halo.filter(ImageFilter.GaussianBlur(size * 0.045))
        canvas = Image.alpha_composite(canvas, halo)

    # Planet layer (later clipped to the sphere)
    planet = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    planet.paste(vertical_gradient(2 * r, OCEAN_TOP, OCEAN_BOTTOM), (cx - r, cy - r))

    land = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    land_draw = ImageDraw.Draw(land)
    for i, (x1, y1, x2, y2) in enumerate(BLOBS):
        land_draw.ellipse(
            [cx + x1 * r, cy + y1 * r, cx + x2 * r, cy + y2 * r],
            fill=LAND_COLORS[i % len(LAND_COLORS)] + (255,),
        )
    land = land.filter(ImageFilter.GaussianBlur(max(1, r * 0.02)))
    planet = Image.alpha_composite(planet, land)

    # Night side (bottom-right falls into shadow)
    tint = Image.new('RGBA', (size, size), (2, 6, 16, 255))
    tint.putalpha(diagonal_ramp(size, 0, 215))
    planet = Image.alpha_composite(planet, tint)

    # Soft specular highlight from the top-left light source
    highlight = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(highlight).ellipse(
        [cx - r * 0.86, cy - r * 0.92, cx + r * 0.08, cy + r * 0.02],
        fill=(255, 255, 255, 55),
    )
    highlight = highlight.filter(ImageFilter.GaussianBlur(r * 0.16))
    planet = Image.alpha_composite(planet, highlight)

    # Atmospheric rim
    rim = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    w = max(2, int(r * 0.035))
    ImageDraw.Draw(rim).ellipse(
        [cx - r + w, cy - r + w, cx + r - w, cy + r - w],
        outline=(190, 235, 255, 195),
        width=w,
    )
    rim = rim.filter(ImageFilter.GaussianBlur(SS))
    planet = Image.alpha_composite(planet, rim)

    # Clip the planet layer to the sphere and flatten
    sphere = Image.new('L', (size, size), 0)
    ImageDraw.Draw(sphere).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    canvas = Image.composite(planet, canvas, sphere)

    return canvas.resize((n, n), Image.LANCZOS)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    specs = [
        ('icon-192x192.png', 192, {'bg': None, 'ratio': 0.82}),
        ('icon-512x512.png', 512, {'bg': None, 'ratio': 0.82}),
        ('maskable-512x512.png', 512, {'bg': VOID_RGB, 'ratio': 0.56}),
        ('apple-touch-icon-180x180.png', 180, {'bg': VOID_RGB, 'ratio': 0.72}),
    ]
    for name, size, kwargs in specs:
        icon = build_icon(size, **kwargs)
        path = OUT_DIR / name
        icon.save(path, 'PNG', optimize=True)
        print(f'wrote {path.relative_to(OUT_DIR.parents[1])} ({size}x{size})')


if __name__ == '__main__':
    main()
