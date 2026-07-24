# SMM Agent 🤖

Kiçik bizneslər üçün süni intelekt əsaslı sosial media köməkçisi.
Brendinin üslubunu öyrənir, Instagram postları (mətn + şəkil) hazırlayır və
Telegram üzərindən sənin təsdiqinə göndərir.

**Beyin:** Google Gemini (AI Studio pulsuz tier — gündə 1500 sorğu) və ya
Anthropic Claude. `.env`-də `AI_PROVIDER` ilə seçilir.

## Quraşdırma

1. **Python 3.11+** quraşdırılmış olmalıdır.

2. Asılılıqları quraşdır:
   ```
   cd smm-agent
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Açarları hazırla:
   - **Gemini (pulsuz):** [aistudio.google.com](https://aistudio.google.com) → *Get API key*
   - **Telegram bot:** Telegram-da [@BotFather](https://t.me/BotFather)-ə `/newbot` yaz → token al
   - **Öz Telegram ID-n:** [@userinfobot](https://t.me/userinfobot)-a bir mesaj yaz

4. `.env.example` faylını `.env` adı ilə kopyala və açarları doldur.

5. Brend profilini redaktə et: `data/brand_profile.json` — öz biznesinin
   məlumatlarını yaz (ton, mövzular, hashtag-lar). Bu, sistemin "beynidir".

6. (İstəyə bağlı) Canva şablonunu qoy: Canva-da dizaynını **mətnsiz** PNG kimi
   eksport et → `data/templates/template1.png` adı ilə saxla. Mətnin yeri/ölçüsü
   `data/templates/template_config.json`-da tənzimlənir. Şablon olmasa, sadə
   gradient fon istifadə olunur.

7. İşə sal:
   ```
   python main.py
   ```

## İstifadə

Telegram-da botuna yaz:

| Əmr | Nə edir |
|---|---|
| `/yeni` | AI mövzu seçib post hazırlayır (şəkil + caption + hashtag) |
| `/yeni yay endirimi` | Verilən mövzuda post hazırlayır |
| `/siyahi` | Son postlar və statusları |

Hər postun altında düymələr: **✅ Təsdiq** / **🔄 Yenidən** / **❌ Rədd et**.
Təsdiqlənmiş postlar bazada saxlanılır və şəkilləri `data/output/` qovluğundadır —
hazır halda Instagram-a yükləyə bilərsən.

## Yol xəritəsi (növbəti mərhələlər)

- [ ] **Mərhələ 2:** Gündəlik avtomatik post təklifi (planlayıcı)
- [ ] **Mərhələ 3:** Instagram Graph API ilə avtomatik paylaşım
- [ ] **Mərhələ 4:** Şərhləri izləmə və cavab layihələri
- [ ] **Mərhələ 5:** Statistika və hesabatlar

## Struktur

```
smm-agent/
├── main.py              # Giriş nöqtəsi
├── smm/
│   ├── config.py        # Konfiqurasiya (.env)
│   ├── brain.py         # AI beyin (Gemini / Claude)
│   ├── imager.py        # Şablon üzərinə mətn yazan modul
│   ├── bot.py           # Telegram bot (təsdiq axını)
│   └── db.py            # SQLite verilənlər bazası
└── data/
    ├── brand_profile.json   # Brendin üslub pasportu
    ├── templates/           # Canva şablonları (PNG)
    └── output/              # Hazır post şəkilləri
```
