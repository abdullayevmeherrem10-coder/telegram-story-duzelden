"""SMM Agent — giriş nöqtəsi. İşə salmaq: python main.py"""
import logging
import sys

from smm import bot, config, db

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)


def main():
    missing = config.validate()
    if missing:
        print("⚠️  .env faylında bu dəyərlər çatışmır:", ", ".join(missing))
        print("   .env.example faylını .env adı ilə kopyalayıb doldurun.")
        sys.exit(1)

    db.init()
    app = bot.build_app()
    print(f"🤖 SMM Agent işə düşdü (beyin: {config.AI_PROVIDER}). "
          "Telegram-da botuna /start yaz.")
    app.run_polling()


if __name__ == "__main__":
    main()
