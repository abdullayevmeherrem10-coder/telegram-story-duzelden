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

6. Şablonlar `data/templates/` qovluğundadır (mətnsiz PNG, 1080×1080):
   - `template1.png` — AZ, dırnaqlar arasında sol tərəfdə stat
   - `template2.png` — AZ, yuxarıdakı düzbucaqlı daxilində stat
   - `template3.png` — AZ, mavi-yaşıl qutuda kiçik hərflərlə stat
   - `template4.png` — AZ, tünd yaşıl ləkədə dırnaq ilə xətt arasında stat
   - `template5.png` — AZ, başın sağında ağ zolaqlar üstündə qara stat
   - `template6.png` — AZ, dırnaq altında iki üfüqi xətt arasında, 2-ci sətir qızılı
   - `template7.png` — AZ, açıq kartda dırnaq altında, "Mütəxəssis parapsixoloq"
     sözündən bir sətir yuxarıda bitir
   - `template8.png` — AZ, dırnaq altında iki xətt arasında, hər 2-ci sətir yaşıl
   - `template9.png` — AZ, aşağıdakı qara düzbucaqlıda ağ yazı
   - `template10.png` — AZ, dırnaq altındakı göy çərçivədə ağ yazı
   - `template6_numune.png` … `template10_numune.png` — həmin şablonların yazı
     nümunələri (yalnız istinad üçün, koddan istifadə olunmur)
   - `template_ru1.png`, `template_ru2.png` — rusca statlar, template1/4-ün
     rusca versiyaları, gün-gün növbə ilə

   Gündəlik paketdə AZ statları gün-gün növbələşir: template1 → 2 → … → 10. Rusca statlar yalnız ru1 ↔ ru2.
   Mətnin yeri, ölçüsü
   və rəngləri `data/templates/template_config.json`-da tənzimlənir
   (`az1`–`az10`, `ru1`, `ru2` açarları). Bütün sətirlər eyni ölçüdə yazılır;
   template1/2-də 2-ci sətir vurğu rəngi ilə.

7. İşə sal:
   ```
   python main.py
   ```

## İstifadə

Telegram-da botuna yaz:

| Əmr | Nə edir |
|---|---|
| `/yeni` | 16 mövzudan biri seçilir, sonra şablon (növbə ilə və ya 1–10) |
| `/yeni yay endirimi` | Verilən mövzuda post hazırlayır (şablon seçimi ilə) |
| `/rusca` | Rusca stat postu, şablon növbə ilə ru1 ↔ ru2 |
| `/gundelik` | Günün paketi (4 AZ + 1 RU), şablon gün-gün 1→2→…→10 |
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
