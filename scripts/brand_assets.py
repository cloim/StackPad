"""Shared pastel four-pad mark with platform-specific mask safety."""
from PIL import Image, ImageDraw

BACKGROUND = '#efeee5'
COLORS = ('#9caf9f', '#9eb4c3', '#b4a9c6', '#cbb493')


def make_icon(size, *, foreground=False, maskable=False):
    canvas_size = 1024
    image = Image.new('RGBA', (canvas_size, canvas_size), BACKGROUND if maskable else (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if not foreground and not maskable:
        draw.rounded_rectangle((4, 4, 1019, 1019), radius=200, fill=BACKGROUND)
    # Android crops a 108dp foreground to a 66dp safe circle. A 44dp mark fits even at its corners.
    extent = canvas_size * (0.40625 if foreground else 0.5625)
    gap = extent / 9
    side = (extent - gap) / 2
    start = (canvas_size - extent) / 2
    for index, color in enumerate(COLORS):
        x = start + (index % 2) * (side + gap)
        y = start + (index // 2) * (side + gap)
        draw.rounded_rectangle((x, y, x + side, y + side), radius=side * .16, fill=color)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def favicon_svg():
    pads = ''.join(f'<rect x="{x}" y="{y}" width="16" height="16" rx="2.6" fill="{color}"/>'
                   for (x, y), color in zip(((14, 14), (34, 14), (14, 34), (34, 34)), COLORS))
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="1" y="1" width="62" height="62" rx="13" fill="{BACKGROUND}"/>{pads}</svg>\n'
