"""Build Android launcher icons and splash screens from the PWA icons."""
from pathlib import Path
from PIL import Image, ImageDraw
from brand_assets import BACKGROUND, COLORS, make_icon

root = Path(__file__).resolve().parents[1]
res = root / 'android/app/src/main/res'
icon = Image.open(root / 'public/pwa-512.png').convert('RGBA')
maskable = Image.open(root / 'public/pwa-maskable-512.png').convert('RGBA')
background = BACKGROUND

for density, scale in {'mdpi': 1, 'hdpi': 1.5, 'xhdpi': 2, 'xxhdpi': 3, 'xxxhdpi': 4}.items():
    folder = res / f'mipmap-{density}'
    legacy = round(48 * scale)
    icon.resize((legacy, legacy), Image.LANCZOS).save(folder / 'ic_launcher.png')
    round_icon = maskable.resize((legacy, legacy), Image.LANCZOS)
    mask = Image.new('L', (legacy, legacy))
    ImageDraw.Draw(mask).ellipse((0, 0, legacy - 1, legacy - 1), fill=255)
    round_icon.putalpha(mask)
    round_icon.save(folder / 'ic_launcher_round.png')
    # Foreground artwork stays inside the 66dp safe circle of the full 108dp adaptive layer.
    foreground = round(108 * scale)
    make_icon(foreground, foreground=True).save(folder / 'ic_launcher_foreground.png')

for splash in res.glob('drawable*/splash.png'):
    width, height = Image.open(splash).size
    canvas = Image.new('RGBA', (width, height), background)
    size = min(width, height) // 4
    canvas.alpha_composite(icon.resize((size, size), Image.LANCZOS), ((width - size) // 2, (height - size) // 2))
    canvas.convert('RGB').save(splash)

(res / 'values/ic_launcher_background.xml').write_text(f'<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">{BACKGROUND}</color>\n</resources>\n', 'utf-8')
(res / 'drawable/ic_launcher_background.xml').write_text(f'<?xml version="1.0" encoding="utf-8"?>\n<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle"><solid android:color="{BACKGROUND}"/></shape>\n', 'utf-8')
paths = []
for (x, y), color in zip(((32, 32), (56, 32), (32, 56), (56, 56)), COLORS):
    paths.append(f'<path android:fillColor="{color}" android:pathData="M{x+3},{y}h14a3,3 0 0,1 3,3v14a3,3 0 0,1 -3,3h-14a3,3 0 0,1 -3,-3v-14a3,3 0 0,1 3,-3Z"/>')
(res / 'drawable-v24/ic_launcher_foreground.xml').write_text('<?xml version="1.0" encoding="utf-8"?>\n<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="108dp" android:height="108dp" android:viewportWidth="108" android:viewportHeight="108">' + ''.join(paths) + '</vector>\n', 'utf-8')
print('Android icons and splash screens generated')
