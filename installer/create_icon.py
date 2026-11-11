"""Generate the GNS Downloader Windows application icon."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main():
    output = Path(__file__).with_name("gns-downloader.ico")
    sizes = (16, 24, 32, 48, 64, 128, 256)
    image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((7, 7, 249, 249), radius=48, fill="#FFFFFF", outline="#E2231A", width=8)
    font_path = Path("C:/Windows/Fonts/arialbd.ttf")
    if not font_path.exists():
        font_path = Path("C:/Windows/Fonts/segoeuib.ttf")
    font = ImageFont.truetype(str(font_path), 188) if font_path.exists() else ImageFont.load_default()
    bounds = draw.textbbox((0, 0), "G", font=font, stroke_width=0)
    x = (256 - (bounds[2] - bounds[0])) / 2 - bounds[0] - 2
    y = (256 - (bounds[3] - bounds[1])) / 2 - bounds[1] - 8
    draw.text((x, y), "G", font=font, fill="#E2231A", stroke_width=0)
    image.save(output, format="ICO", sizes=[(size, size) for size in sizes])
    print(f"Created {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
