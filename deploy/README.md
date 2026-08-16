# Serverə yerləşdirmə

> **Hazırkı vəziyyət:** bot **PythonAnywhere**-də işləyir. Aşağıdakı VPS
> təlimatı gələcəkdə klassik serverə (Ubuntu/Debian) keçmək lazım olsa
> keçərlidir — icra zamanı bu qovluqdakı heç bir fayl istifadə olunmur.

## PythonAnywhere (hazırkı hosting)

Bot **Always-on task** kimi işləyir — düşəndə platforma özü qaldırır.
İdarəetmə [pythonanywhere.com](https://www.pythonanywhere.com) veb-panelindən gedir:

- Kodu yenilə: Bash konsolunda `cd ~/smm-agent && git pull`
- Botu yenidən başlat: **Tasks** səhifəsində always-on task-ın yanındakı
  restart düyməsi (və ya API: `POST .../always_on/<id>/restart/`)
- Loglar: **Tasks** səhifəsində task-ın log linki
  (`/var/log/alwayson-log-<id>.log`)

⚠️ Konsolda `python main.py` İŞLƏTMƏ — always-on nüsxə ilə
`Conflict: terminated by other getUpdates request` toqquşması yaranır.
Konsol yalnız `git pull` və fayl işləri üçündür.

Qeyd: PythonAnywhere şəbəkəsi yavaş ola bildiyindən Telegram
timeout-ları kodda genişləndirilib (media 180 san).

## Alternativ: öz VPS-in (Ubuntu/Debian)

Botu istənilən Ubuntu/Debian serverdə 24/7 işlədir. `systemd` ilə qurulur —
server yenidən başlasa və ya bot düşsə, özü avtomatik qalxır.

**1. Serverə qoşul**

```bash
ssh -i ~/.ssh/ACAR_FAYLI ubuntu@SERVER_IP
```

**2. Layihəni götür**

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/abdullayevmeherrem10-coder/telegram-story-duzelden.git smm-agent
```

**3. `.env` faylını köçür**

`.env` git-ə düşmür (açarlar var), ona görə ayrıca göndərilir.
Bu əmr **lokal kompüterdə** işlədilir:

```powershell
scp -i $env:USERPROFILE\.ssh\ACAR_FAYLI yol\smm-agent\.env ubuntu@SERVER_IP:~/smm-agent/.env
```

**4. Quraşdır**

```bash
cd ~/smm-agent
bash deploy/install.sh
```

Skript hər şeyi özü edir: Python, virtual mühit, asılılıqlar, `.env` yoxlaması,
systemd servisi. Sonda vəziyyəti göstərir.

**Gündəlik istifadə:**

```bash
sudo systemctl status smm-agent      # işləyir, ya yox
sudo journalctl -u smm-agent -f      # canlı loglar
sudo systemctl restart smm-agent     # yenidən başlat
sudo systemctl stop smm-agent        # dayandır
```

**Kodu yeniləmək:**

```bash
cd ~/smm-agent
git pull
sudo systemctl restart smm-agent
```

## ⚠️ Vacib: eyni anda yalnız BİR nüsxə işləməlidir

Telegram bir botun `getUpdates` axınına yalnız bir müştəri buraxır. İki yerdə
(məsələn, PythonAnywhere + lokal kompüter) eyni vaxtda işləsə, ikisi də
növbə ilə xəta verəcək:

```
Conflict: terminated by other getUpdates request
```

Lokalda test etmək lazım olanda əvvəlcə serverdəki nüsxəni dayandır.

## Nə saxlanılır

- `data/smm.db` — postlar və statuslar (git-ə düşmür)
- `data/output/` — hazır post şəkilləri (git-ə düşmür)

Serveri dəyişəndə bu iki qovluğu köçürmək kifayətdir.
