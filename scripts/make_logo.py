#!/usr/bin/env python3
"""v1.8 logo — AI Trading Lab: 3 ascending candles + gold trend arrow on dark rounded square."""
from PIL import Image, ImageDraw
import os

RES = "/home/z/my-project/android-app/app/src/main/res"
S = 1024  # master size

def rounded_bg(size, radius_pct=0.225):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(size * radius_pct)
    # vertical gradient navy
    grad = Image.new("RGBA", (size, size))
    gd = ImageDraw.Draw(grad)
    top, bot = (13, 18, 32), (22, 34, 56)
    for y in range(size):
        t = y / size
        gd.line([(0, y), (size, y)], fill=(
            int(top[0] + (bot[0] - top[0]) * t),
            int(top[1] + (bot[1] - top[1]) * t),
            int(top[2] + (bot[2] - top[2]) * t), 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=255)
    img.paste(grad, (0, 0), mask)
    return img, d, r

def draw_logo(size):
    img, d, r = rounded_bg(size)
    u = size / 100.0  # unit
    # subtle inner glow circle
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([size*0.08, size*0.02, size*0.92, size*0.86], fill=(56, 130, 246, 26))
    from PIL import ImageFilter
    glow = glow.filter(ImageFilter.GaussianBlur(size*0.05))
    img.alpha_composite(glow)

    # 3 ascending candles (green) + rising heights
    green = (16, 185, 129, 255)
    green_dark = (5, 150, 105, 255)
    candles = [  # (cx, body_top, body_bottom, wick_top, wick_bottom, w) in units
        (32, 56, 74, 50, 80, 7.5),
        (50, 44, 64, 38, 70, 7.5),
        (68, 28, 52, 22, 58, 7.5),
    ]
    for cx, bt, bb, wt, wb, w in candles:
        x0, x1 = (cx - w/2)*u, (cx + w/2)*u
        # wick
        d.line([(cx*u, wt*u), (cx*u, wb*u)], fill=green, width=max(2, int(2.2*u)))
        # body with slight gradient effect (two tones)
        d.rounded_rectangle([x0, bt*u, x1, bb*u], radius=w/2*u*0.6, fill=green)
        # subtle bottom shade
        d.rounded_rectangle([x0, (bb-4)*u, x1, bb*u], radius=w/2*u*0.6, fill=green_dark)
    # gold trend arrow from candle1 to beyond candle3
    gold = (240, 180, 41, 255)
    aw = max(3, int(4.2*u))
    d.line([(24*u, 66*u), (72*u, 34*u)], fill=gold, width=aw)
    # arrowhead
    ax, ay = 72*u, 34*u
    d.polygon([(ax+9*u, ay-14*u), (ax-7*u, ay-6*u), (ax+2*u, ay+8*u)], fill=gold)
    # small base dot grid (data feel)
    for gx in (18, 30, 42):
        d.ellipse([gx*u-1.4*u, 86*u-1.4*u, gx*u+1.4*u, 86*u+1.4*u], fill=(120, 145, 185, 90))
    return img

def draw_round(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    full = draw_logo(size)
    # circular mask on the rendered logo (re-render flat bg for circle)
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(bg)
    grad = Image.new("RGBA", (size, size))
    gd = ImageDraw.Draw(grad)
    top, bot = (13, 18, 32), (22, 34, 56)
    for y in range(size):
        t = y / size
        gd.line([(0, y), (size, y)], fill=(
            int(top[0]+(bot[0]-top[0])*t), int(top[1]+(bot[1]-top[1])*t),
            int(top[2]+(bot[2]-top[2])*t), 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size-1, size-1], fill=255)
    bg.paste(grad, (0, 0), mask)
    # redraw candles/arrow on the circular bg (reuse draw at same coords)
    d2 = ImageDraw.Draw(bg)
    u = size / 100.0
    green = (16, 185, 129, 255); green_dark = (5, 150, 105, 255)
    for cx, bt, bb, wt, wb, w in [(32,56,74,50,80,7.5),(50,44,64,38,70,7.5),(68,28,52,22,58,7.5)]:
        x0, x1 = (cx-w/2)*u, (cx+w/2)*u
        d2.line([(cx*u, wt*u), (cx*u, wb*u)], fill=green, width=max(2, int(2.2*u)))
        d2.rounded_rectangle([x0, bt*u, x1, bb*u], radius=w/2*u*0.6, fill=green)
        d2.rounded_rectangle([x0, (bb-4)*u, x1, bb*u], radius=w/2*u*0.6, fill=green_dark)
    gold = (240, 180, 41, 255); aw = max(3, int(4.2*u))
    d2.line([(24*u, 66*u), (72*u, 34*u)], fill=gold, width=aw)
    ax, ay = 72*u, 34*u
    d2.polygon([(ax+9*u, ay-14*u), (ax-7*u, ay-6*u), (ax+2*u, ay+8*u)], fill=gold)
    return bg

master = draw_logo(S)
dens = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
for dpi, px in dens.items():
    folder = f"{RES}/mipmap-{dpi}"
    os.makedirs(folder, exist_ok=True)
    master.resize((px, px), Image.LANCZOS).save(f"{folder}/ic_launcher.png")
    draw_round(px).save(f"{folder}/ic_launcher_round.png")
# dashboard header logo
master.resize((256, 256), Image.LANCZOS).save("/home/z/my-project/android-app/app/src/main/assets/logo.png")
print("ICONS DONE:", list(dens.items()), "+ assets/logo.png (256)")
