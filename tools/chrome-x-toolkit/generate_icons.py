#!/usr/bin/env python3
"""生成 X 工具箱占位图标。运行: python generate_icons.py"""

from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("pip install Pillow")
    raise SystemExit(1)


def create_icon(size: int, output_path: Path) -> None:
    img = Image.new("RGB", (size, size), color="#1D9BF0")
    draw = ImageDraw.Draw(img)
    margin = size // 5
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=size // 6,
        fill="white",
    )
    # X 形
    inner = margin + size // 8
    draw.line([inner, inner, size - inner, size - inner], fill="#1D9BF0", width=max(2, size // 10))
    draw.line([size - inner, inner, inner, size - inner], fill="#1D9BF0", width=max(2, size // 10))
    img.save(output_path, "PNG")
    print(f"OK {output_path} ({size}x{size})")


def main() -> None:
    icons_dir = Path(__file__).parent / "icons"
    icons_dir.mkdir(exist_ok=True)
    for size in (16, 48, 128):
        create_icon(size, icons_dir / f"icon{size}.png")


if __name__ == "__main__":
    main()
