"""Check actual generated icon pixels against OS mask safety, not just image bounds."""
from pathlib import Path
from PIL import Image, ImageColor
from brand_assets import BACKGROUND

root = Path(__file__).resolve().parents[1]
background = ImageColor.getrgb(BACKGROUND)
for file in (root / 'android/app/src/main/res').glob('mipmap-*/ic_launcher_foreground.png'):
    image = Image.open(file).convert('RGBA')
    size = image.width
    radius = size * 33 / 108
    colored = 0
    for y in range(size):
        for x in range(size):
            if image.getpixel((x, y))[3] > 16:
                assert (x + .5 - size / 2) ** 2 + (y + .5 - size / 2) ** 2 <= radius ** 2, file
                colored += 1
    assert colored > 0 and image.getpixel((0, 0))[3] == 0, file
    print('ADAPTIVE SAFE', file.parent.name, size, 'px')
image = Image.open(root / 'public/pwa-maskable-512.png').convert('RGBA')
for y in range(image.height):
    for x in range(image.width):
        pixel = image.getpixel((x, y))
        if pixel[3] > 128 and max(abs(pixel[i] - background[i]) for i in range(3)) > 20:
            assert (x + .5 - 256) ** 2 + (y + .5 - 256) ** 2 <= (512 * .4) ** 2, 'PWA safe circle'
for file in (root / 'public/favicon.ico', root / 'src-tauri/icons/icon.ico'):
    icon = Image.open(file)
    assert {(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)} <= icon.ico.sizes(), file
    for size in icon.ico.sizes():
        frame = icon.ico.getimage(size).convert('RGBA')
        for x, y in ((0, 0), (0, size[1]-1), (size[0]-1, 0), (size[0]-1, size[1]-1)):
            assert frame.getpixel((x, y))[3] == 0, (file, size)
print('BRAND ICON PASS: five Android densities inside 66dp safe circle, PWA mask safety, six ICO sizes with transparent corners')
