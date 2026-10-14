"""Build Android launcher icons and splash screens from the PWA icons."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1]
res = root / 'android/app/src/main/res'
icon = Image.open(root / 'public/pwa-512.png').convert('RGBA')
maskable = Image.open(root / 'public/pwa-maskable-512.png').convert('RGBA')
background = (0x20, 0x21, 0x22, 255)

for density, scale in {'mdpi': 1, 'hdpi': 1.5, 'xhdpi': 2, 'xxhdpi': 3, 'xxxhdpi': 4}.items():
    folder = res / f'mipmap-{density}'
    legacy = round(48 * scale)
    icon.resize((legacy, legacy), Image.LANCZOS).save(folder / 'ic_launcher.png')
    round_icon = maskable.resize((legacy, legacy), Image.LANCZOS)
    mask = Image.new('L', (legacy, legacy))
    ImageDraw.Draw(mask).ellipse((0, 0, legacy - 1, legacy - 1), fill=255)
    round_icon.putalpha(mask)
    round_icon.save(folder / 'ic_launcher_round.png')
    # Adaptive icons crop a 108dp layer to its inner 72dp, the same safe zone as a maskable PWA icon.
    foreground = round(108 * scale)
    maskable.resize((foreground, foreground), Image.LANCZOS).save(folder / 'ic_launcher_foreground.png')

for splash in res.glob('drawable*/splash.png'):
    width, height = Image.open(splash).size
    canvas = Image.new('RGBA', (width, height), background)
    size = min(width, height) // 4
    canvas.alpha_composite(icon.resize((size, size), Image.LANCZOS), ((width - size) // 2, (height - size) // 2))
    canvas.convert('RGB').save(splash)

(res / 'values/ic_launcher_background.xml').write_text('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">#202122</color>\n</resources>\n', 'utf-8')
print('Android icons and splash screens generated')
