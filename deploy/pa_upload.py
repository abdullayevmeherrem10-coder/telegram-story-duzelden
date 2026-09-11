"""PythonAnywhere-ə fayl yükləmə və botu yenidən başlatma (API ilə).

Şablon PNG-ləri və brand_profile git-ə düşmür (.gitignore), ona görə onlar
yalnız bu yolla serverə gedir. Kod faylları da eyni yolla göndərilə bilər —
git pull gözləmək lazım deyil.

İstifadə (lokal kompüterdə, layihə kökündən):

    set PA_USERNAME=pythonanywhere_istifadeci_adi
    set PA_API_TOKEN=xxxxxxxxxxxxxxxx          (Account -> API Token)
    python deploy/pa_upload.py                 # standart fayl siyahısı
    python deploy/pa_upload.py smm/bot.py      # yalnız verilən fayllar
    python deploy/pa_upload.py --no-restart    # yükləsin, restart etməsin

İstəyə bağlı: PA_HOST (standart www.pythonanywhere.com; EU hesab üçün
eu.pythonanywhere.com), PA_REMOTE_DIR (standart smm-agent).
"""
import os
import sys
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent

# Standart olaraq göndərilən fayllar (layihə kökünə görə nisbi yollar)
DEFAULT_FILES = [
    "smm/bot.py",
    "smm/brain.py",
    "smm/imager.py",
    "smm/config.py",
    "smm/db.py",
    "main.py",
    "requirements.txt",
    "README.md",
    "data/brand_profile.json",
    "data/templates/template_config.json",
    "data/templates/template1.png",
    "data/templates/template2.png",
    "data/templates/template3.png",
    "data/templates/template4.png",
    "data/templates/template5.png",
    "data/templates/template6.png",
    "data/templates/template7.png",
    "data/templates/template8.png",
    "data/templates/template9.png",
    "data/templates/template10.png",
    "data/templates/template_ru1.png",
    "data/templates/template_ru2.png",
    "data/templates/fonts/Montserrat-ExtraBold.ttf",
]


def main() -> int:
    username = os.environ.get("PA_USERNAME", "").strip()
    token = os.environ.get("PA_API_TOKEN", "").strip()
    host = os.environ.get("PA_HOST", "www.pythonanywhere.com").strip()
    remote_dir = os.environ.get("PA_REMOTE_DIR", "smm-agent").strip("/")
    if not username or not token:
        print("XƏTA: PA_USERNAME və PA_API_TOKEN mühit dəyişənləri lazımdır.")
        return 1

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    restart = "--no-restart" not in sys.argv
    files = args or DEFAULT_FILES

    api = f"https://{host}/api/v0/user/{username}"
    headers = {"Authorization": f"Token {token}"}

    failed = 0
    for rel in files:
        local = BASE_DIR / rel
        if not local.exists():
            print(f"  ⏭  {rel} — lokalda yoxdur, ötürüldü")
            continue
        remote_path = f"/home/{username}/{remote_dir}/{rel}"
        with open(local, "rb") as f:
            r = requests.post(f"{api}/files/path{remote_path}",
                              headers=headers, files={"content": f}, timeout=120)
        if r.status_code in (200, 201):
            print(f"  ✅ {rel}  ({local.stat().st_size // 1024} KB)")
        else:
            failed += 1
            print(f"  ❌ {rel} — HTTP {r.status_code}: {r.text[:200]}")

    if failed:
        print(f"\n{failed} fayl yüklənmədi, restart edilmir.")
        return 1

    if not restart:
        print("\nYükləmə bitdi (restart edilmədi).")
        return 0

    r = requests.get(f"{api}/always_on/", headers=headers, timeout=60)
    if r.status_code != 200:
        print(f"\nAlways-on task siyahısı alınmadı: HTTP {r.status_code}: {r.text[:200]}")
        return 1
    tasks = r.json()
    bot_tasks = [t for t in tasks if "main.py" in t.get("command", "")] or tasks
    if not bot_tasks:
        print("\nAlways-on task tapılmadı — botu veb-paneldən yenidən başlat.")
        return 1
    for t in bot_tasks:
        rr = requests.post(f"{api}/always_on/{t['id']}/restart/", headers=headers, timeout=60)
        status = "✅" if rr.status_code in (200, 201, 204) else f"❌ HTTP {rr.status_code}"
        print(f"\n🔄 Restart: task #{t['id']} «{t.get('command', '')[:60]}» — {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
