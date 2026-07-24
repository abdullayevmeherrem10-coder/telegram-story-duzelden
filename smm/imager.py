"""Şəkil modulu — Canva şablonu üzərinə statı (aforizmi) yazır.

Stat şablonun yuxarı hissəsindəki boş sahəyə (başın üzərinə) mərkəzləşdirilmiş,
böyük hərflərlə, Montserrat ExtraBold şrifti ilə yazılır. Mətn uzun olduqda
şrift ölçüsü avtomatik kiçilir ki, sahəyə sığsın.
"""
import json
import time

from PIL import Image, ImageDraw, ImageFont

from . import config


def _load_template_config(template: str) -> dict:
    with open(config.TEMPLATE_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)[template]


def _az_upper(text: str) -> str:
    # Azərbaycan dilində i -> İ, ı -> I (Python .upper() bunu səhv edir)
    return text.replace("i", "İ").replace("ı", "I").upper()


def _wrap(draw: ImageDraw.ImageDraw, text: str,
          font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font_path: str,
              spec: dict) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """Mətnə sahəyə sığan ən böyük şrift ölçüsünü tapır."""
    box_height = spec["box_bottom"] - spec["box_top"]
    for size in range(spec["base_size"], spec["min_size"] - 1, -2):
        font = ImageFont.truetype(font_path, size)
        lines = _wrap(draw, text, font, spec["max_width"])
        line_height = int(size * spec["line_spacing"])
        total_height = line_height * len(lines)
        if len(lines) <= spec["max_lines"] and total_height <= box_height:
            return font, lines, line_height
    # Minimum ölçüdə belə sığmırsa, minimum ilə davam et
    font = ImageFont.truetype(font_path, spec["min_size"])
    lines = _wrap(draw, text, font, spec["max_width"])
    return font, lines, int(spec["min_size"] * spec["line_spacing"])


def render_post_image(quote: str, template: str = "az") -> str:
    """Statı şablon üzərinə yazıb hazır şəklin yolunu qaytarır.

    template: "az" (template1) və ya "ru" (template2).
    """
    cfg = _load_template_config(template)
    spec = cfg["quote"]
    size = tuple(cfg.get("size", [1080, 1080]))

    img = Image.open(config.TEMPLATES_DIR / cfg["file"]).convert("RGB")
    if img.size != size:
        img = img.resize(size)
    draw = ImageDraw.Draw(img)

    text = quote.strip().rstrip(".")
    if spec.get("uppercase", True):
        text = _az_upper(text) if template == "az" else text.upper()

    font_path = str(config.TEMPLATES_DIR / cfg["font"])
    font, lines, line_height = _fit_text(draw, text, font_path, spec)

    # Sahə daxilində şaquli mərkəzləşdirmə
    total_height = line_height * len(lines)
    y = spec["box_top"] + (spec["box_bottom"] - spec["box_top"] - total_height) // 2

    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text((spec["center_x"] - w / 2, y), line,
                  font=font, fill=spec["color"])
        y += line_height

    out_path = config.OUTPUT_DIR / f"post_{template}_{int(time.time() * 1000)}.png"
    img.save(out_path)
    return str(out_path)
