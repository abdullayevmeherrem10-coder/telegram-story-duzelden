"""Şəkil modulu — Canva şablonu üzərinə statı (aforizmi) yazır.

Stat şablonun boş sahəsinə (template_config.json-da "quote" bloku ilə
təyin olunur) böyük hərflərlə, Montserrat ExtraBold şrifti ilə yazılır.
Mətn uzun olduqda şrift ölçüsü avtomatik kiçilir ki, sahəyə sığsın;
bütün sətirlər EYNİ ölçüdə olur.

Şablonlar: az (template1), ru (template2), az3 (template3, sol tərəfdə
dırnaqlar arasında), az4 (template4, yuxarıdakı düzbucaqlı daxilində),
az5 (template5, mavi-yaşıl qutuda, kiçik hərflərlə), az6 (template6, tünd
yaşıl ləkədə dırnaq ilə narıncı xətt arasında). az5/az6-da mətn sahəsi
mütəxəssisin şəklinə toxunmayacaq şəkildə daraldılıb.
"quote" blokunda: align = "center" | "left"; accent_line = rənglənən sətrin
indeksi (nümunədəki kimi 2-ci sətir vurğu rəngi ilə), accent_color = həmin rəng.
"""
import json
import logging
import os
import time

from PIL import Image, ImageDraw, ImageFont

from . import config

logger = logging.getLogger(__name__)


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


def prune_old_outputs(days: int | None = None) -> int:
    """Köhnə post şəkillərini silir və silinən sayını qaytarır.

    Kiçik diskli hostinqlərdə (məs. PythonAnywhere — 1 GB) şəkillər ayda
    ~150 MB yığır və nəhayət disk dolur. Hər yeni şəkildən sonra çağırılır.
    """
    days = config.OUTPUT_RETENTION_DAYS if days is None else days
    if days <= 0:
        return 0

    cutoff = time.time() - days * 86400
    removed = 0
    try:
        entries = list(os.scandir(config.OUTPUT_DIR))
    except OSError:
        return 0

    for entry in entries:
        if not entry.is_file() or not entry.name.endswith(".png"):
            continue
        try:
            if entry.stat().st_mtime < cutoff:
                os.remove(entry.path)
                removed += 1
        except OSError:
            # Fayl paralel silinib və ya kilidlidir — problem deyil
            continue

    if removed:
        logger.info("%s köhnə post şəkli silindi (%s gündən köhnə)",
                    removed, days)
    return removed


def render_post_image(quote: str, template: str = "az") -> str:
    """Statı şablon üzərinə yazıb hazır şəklin yolunu qaytarır.

    template: template_config.json-dakı açar ("az", "ru", "az3", "az4").
    """
    cfg = _load_template_config(template)
    spec = cfg["quote"]
    size = tuple(cfg.get("size", [1080, 1080]))
    lang = cfg.get("lang", "ru" if template == "ru" else "az")

    img = Image.open(config.TEMPLATES_DIR / cfg["file"]).convert("RGB")
    if img.size != size:
        img = img.resize(size)
    draw = ImageDraw.Draw(img)

    text = quote.strip().rstrip(".")
    if spec.get("uppercase", True):
        text = _az_upper(text) if lang == "az" else text.upper()

    font_path = str(config.TEMPLATES_DIR / cfg["font"])
    font, lines, line_height = _fit_text(draw, text, font_path, spec)

    # Sahə daxilində şaquli mərkəzləşdirmə
    total_height = line_height * len(lines)
    y = spec["box_top"] + (spec["box_bottom"] - spec["box_top"] - total_height) // 2

    align = spec.get("align", "center")
    accent_line = spec.get("accent_line")
    accent_color = spec.get("accent_color", spec["color"])

    for i, line in enumerate(lines):
        if align == "left":
            x = spec["left_x"]
        else:
            x = spec["center_x"] - draw.textlength(line, font=font) / 2
        # Vurğu sətri yalnız çoxsətirli statda (tək sətir əsas rəngdə qalır)
        color = accent_color if (accent_line is not None and len(lines) > 1
                                 and i == accent_line) else spec["color"]
        draw.text((x, y), line, font=font, fill=color)
        y += line_height

    out_path = config.OUTPUT_DIR / f"post_{template}_{int(time.time() * 1000)}.png"
    img.save(out_path)
    prune_old_outputs()
    return str(out_path)
