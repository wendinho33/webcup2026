"""Generate the TerraX coin icon (Pillow) to match terrax.svg.

Run from the project root:

    env/bin/python tools/generate_terrax_icon.py

Outputs into static/img/terrax/:
    terrax-512.png  terrax-192.png  terrax-64.png  terrax-32.png
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT_DIR = Path(__file__).resolve().parents[1] / 'static' / 'img' / 'terrax'
SS = 4  # supersample factor

AMBER = (255, 178, 87)
AMBER_LIGHT = (255, 231, 184)
AMBER_DARK = (217, 123, 28)
RIM = (92, 58, 14)
INK = (20, 12, 3)


def build(size):
    px = size * SS
    canvas = Image.new('RGBA', (px, px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    cx = cy = px // 2
    r = int(px * 0.48)

    # rim + face
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=RIM + (255,))
    face = int(r * 0.92)
    draw.ellipse(
        [cx - face, cy - face, cx + face, cy + face],
        fill=AMBER + (255,),
    )

    # soft radial feel: light top-left, warm shadow bottom-right
    glow = Image.new('RGBA', (px, px), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse(
        [cx - face * 0.9, cy - face * 0.95, cx + face * 0.15, cy + face * 0.05],
        fill=AMBER_LIGHT + (190,),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(px * 0.05))
    canvas = Image.alpha_composite(canvas, glow)

    shade = Image.new('RGBA', (px, px), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    sd.ellipse(
        [cx - face * 0.1, cy - face * 0.1, cx + face, cy + face],
        fill=AMBER_DARK + (200,),
    )
    shade = shade.filter(ImageFilter.GaussianBlur(px * 0.06))
    canvas = Image.alpha_composite(canvas, shade)

    draw = ImageDraw.Draw(canvas)

    # inner ring
    ring = int(r * 0.84)
    draw.ellipse(
        [cx - ring, cy - ring, cx + ring, cy + ring],
        outline=INK + (70,),
        width=max(1, int(px * 0.006)),
    )

    # T monogram
    ink_layer = Image.new('RGBA', (px, px), (0, 0, 0, 0))
    td = ImageDraw.Draw(ink_layer)
    bar_w = int(r * 0.78)
    bar_h = int(r * 0.19)
    bar_x = cx - bar_w // 2
    bar_y = int(cy - r * 0.36)
    stem_w = int(r * 0.19)
    stem_top = bar_y + bar_h
    stem_bottom = int(cy + r * 0.55)
    td.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], fill=INK + (235,))
    td.rectangle(
        [cx - stem_w // 2, stem_top, cx + stem_w // 2, stem_bottom],
        fill=INK + (235,),
    )
    canvas = Image.alpha_composite(canvas, ink_layer)

    # orbit ring (tilted, stays inside the face)
    orbit = Image.new('RGBA', (px, px), (0, 0, 0, 0))
    od = ImageDraw.Draw(orbit)
    od.ellipse(
        [cx - int(r * 0.82), cy - int(r * 0.30),
         cx + int(r * 0.82), cy + int(r * 0.30)],
        outline=INK + (128,),
        width=max(1, int(px * 0.008)),
    )
    orbit = orbit.rotate(-18, resample=Image.BICUBIC, center=(cx, cy))
    canvas = Image.alpha_composite(canvas, orbit)

    # specular arc
    spec = Image.new('RGBA', (px, px), (0, 0, 0, 0))
    spd = ImageDraw.Draw(spec)
    spd.arc(
        [int(cx - r * 0.82), int(cy - r * 0.86),
         int(cx + r * 0.28), int(cy + r * 0.32)],
        start=195, end=265,
        fill=(255, 255, 255, 150),
        width=max(2, int(px * 0.012)),
    )
    canvas = Image.alpha_composite(canvas, spec)

    return canvas.resize((size, size), Image.LANCZOS)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for size in (512, 192, 64, 32):
        icon = build(size)
        path = OUT_DIR / f'terrax-{size}.png'
        icon.save(path, 'PNG', optimize=True)
        print(f'wrote {path.name} ({size}x{size})')


if __name__ == '__main__':
    main()
