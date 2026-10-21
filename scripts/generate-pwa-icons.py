"""Generate PWA icons matching the existing four-pad StackPad logo."""
from pathlib import Path
from brand_assets import make_icon, favicon_svg

public = Path(__file__).resolve().parents[1] / 'public'
for name, size in [('pwa-192.png', 192), ('pwa-512.png', 512),
                   ('pwa-maskable-512.png', 512), ('apple-touch-icon.png', 180)]:
    image = make_icon(size, maskable=name in ('pwa-maskable-512.png', 'apple-touch-icon.png'))
    image.save(public / name)
(public / 'favicon.svg').write_text(favicon_svg(), encoding='utf-8')
make_icon(256).save(public / 'favicon.ico', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
desktop = public.parent / 'src-tauri/icons'
desktop.mkdir(exist_ok=True)
make_icon(256).save(desktop / 'icon.png')
make_icon(256).save(desktop / 'icon.ico', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print('Pastel web and desktop icons generated with mask-safe padding')
