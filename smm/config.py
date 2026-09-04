import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = DATA_DIR / "templates"
OUTPUT_DIR = DATA_DIR / "output"
DB_PATH = DATA_DIR / "smm.db"
BRAND_PROFILE_PATH = DATA_DIR / "brand_profile.json"
TEMPLATE_CONFIG_PATH = TEMPLATES_DIR / "template_config.json"

load_dotenv(BASE_DIR / ".env")

AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Vergüllə ayrılmış siyahı: birincinin limiti dolanda növbətiyə keçilir
GEMINI_MODELS = [
    m.strip() for m in os.getenv(
        "GEMINI_MODEL",
        "gemini-3.6-flash,gemini-3.8-flash,gemini-3.7-flash,gemini-3.5-flash,"
        "gemini-3-flash-preview,gemini-3.5-flash-lite,gemini-3.1-flash-lite",
    ).split(",") if m.strip()
]

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
# Vergüllə ayrılmış bir və ya bir neçə Telegram ID - hamısı botu idarə edə bilər
TELEGRAM_ADMIN_IDS = [
    int(x.strip()) for x in os.getenv("TELEGRAM_ADMIN_ID", "").split(",")
    if x.strip().isdigit()
]

# Gündəlik avtomatik post rejimi
DAILY_POST_COUNT = int(os.getenv("DAILY_POST_COUNT", "5"))
DAILY_POST_TIME = os.getenv("DAILY_POST_TIME", "09:00")  # SS:DD formatında
TIMEZONE = os.getenv("TIMEZONE", "Asia/Baku")

# Hazır post şəkilləri neçə gün saxlanılsın (diskin dolmasının qarşısını alır).
# 0 və ya mənfi dəyər -> təmizləmə söndürülür.
OUTPUT_RETENTION_DAYS = int(os.getenv("OUTPUT_RETENTION_DAYS", "30"))

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def validate() -> list[str]:
    """Çatışmayan konfiqurasiya dəyərlərinin siyahısını qaytarır."""
    missing = []
    if AI_PROVIDER == "gemini" and not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    if AI_PROVIDER == "claude" and not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_ADMIN_IDS:
        missing.append("TELEGRAM_ADMIN_ID")
    return missing
