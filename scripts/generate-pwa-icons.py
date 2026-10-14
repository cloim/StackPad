"""Generate PWA icons matching the existing four-pad StackPad logo."""
from pathlib import Path
from PIL import Image, ImageDraw

public = Path(__file__).resolve().parents[1] / 'public'
for name, size in [('pwa-192.png', 192), ('pwa-512.png', 512),
                   ('pwa-maskable-512.png', 512), ('apple-touch-icon.png', 180)]:
    image = Image.new('RGB', (size, size), '#202122')
    draw = ImageDraw.Draw(image)
    # Keep the complete logo inside the central maskable safe zone.
    scale = size / 256
    for x, y, color in [(48, 48, '#efa668'), (136, 48, '#cf8c54'),
                        (48, 136, '#876347'), (136, 136, '#efa668')]:
        draw.rounded_rectangle(tuple(round(v * scale) for v in (x, y, x + 72, y + 72)),
                               radius=round(14 * scale), fill=color)
    image.save(public / name)
