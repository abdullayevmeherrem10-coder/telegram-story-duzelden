"""AI beyin modulu — brend profilinə uyğun stat (aforizm) postları yaradır.

AI_PROVIDER dəyərinə görə Google Gemini (pulsuz tier) və ya
Anthropic Claude istifadə olunur.
"""
import json
import logging
import re

from pydantic import BaseModel

from . import config, db

logger = logging.getLogger(__name__)

# Son uğurlu sorğuda istifadə olunan model (bot bildiriş üçün oxuyur)
last_used_model: str | None = None

# Bilinən gündəlik limitlər — 429 xətalarından avtomatik öyrənilib saxlanılır
LIMITS_PATH = config.DATA_DIR / "limits.json"
_DEFAULT_LIMITS = {"gemini-3.6-flash": 20}


def _load_limits() -> dict:
    try:
        with open(LIMITS_PATH, encoding="utf-8") as f:
            return {**_DEFAULT_LIMITS, **json.load(f)}
    except (OSError, json.JSONDecodeError):
        return dict(_DEFAULT_LIMITS)


def get_limit(model: str) -> int | None:
    return _load_limits().get(model)


def _save_limit(model: str, limit: int):
    limits = _load_limits()
    limits[model] = limit
    with open(LIMITS_PATH, "w", encoding="utf-8") as f:
        json.dump(limits, f, ensure_ascii=False, indent=2)


class PostContent(BaseModel):
    idea: str    # Postun qısa ideyası / mövzusu (daxili istifadə üçün)
    quote: str   # Şəkil üzərinə yazılacaq stat (qısa, emojisiz)
    caption: str # Instagram caption mətni


def _load_brand_profile() -> dict:
    with open(config.BRAND_PROFILE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _system_prompt(brand: dict) -> str:
    return f"""Sən peşəkar sosial media kontent yaradıcısısan. Aşağıdakı şəxsi brend üçün
Instagram STAT postları hazırlayırsan. Brendin üslub pasportu:

{json.dumps(brand, ensure_ascii=False, indent=2)}

Qaydalar:
- quote — şəkil üzərinə yazılacaq statdır: QISA (ideal 6-9 söz, maksimum 11 söz),
  yaddaqalan, şüar kimi kəsərli, aforizm üslubunda, bənzətmə/metafora ilə.
  Uzun izahlı cümlələr YOX — bir nəfəsə oxunan tək fikir. Emojisiz. Dırnaqsız.
- caption — statı 2-3 cümlə ilə açıqlayır, brendin tonunda, sonda yumşaq
  hərəkətə çağırış. Maksimum 2 emoji. Hashtag YAZMA.
- Qadağan olunmuş mövzulardan istifadə etmə."""


def _generate(system: str, prompt: str) -> PostContent:
    global last_used_model
    if config.AI_PROVIDER == "claude":
        import anthropic

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        response = client.messages.parse(
            model=config.CLAUDE_MODEL,
            max_tokens=2048,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=PostContent,
        )
        last_used_model = config.CLAUDE_MODEL
        db.bump_usage(config.CLAUDE_MODEL)
        return response.parsed_output

    from google import genai
    from google.genai import errors as genai_errors
    from google.genai import types

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    last_error = None
    for model in config.GEMINI_MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_schema=PostContent,
                ),
            )
            last_used_model = model
            db.bump_usage(model)
            if response.parsed is None:
                return PostContent.model_validate_json(response.text)
            return response.parsed
        except genai_errors.ServerError as e:
            # 503 və s. = Google tərəfi yüklüdür -> növbəti modelə keç
            logger.warning("Model %s işləmədi (%s), növbətiyə keçilir",
                           model, e.code)
            last_error = e
            continue
        except genai_errors.ClientError as e:
            # 429 = limit dolub, 404 = model mövcud deyil -> növbəti modelə keç
            if e.code in (429, 404):
                if e.code == 429:
                    # Limit növünü ayırd et: sorğu limiti / token limiti /
                    # dəqiqəlik limit. Keçid hamısında olur, amma yalnız
                    # GÜNLÜK SORĞU limitini yadda saxlayırıq (token limitləri
                    # fərqli vahiddir, sayğaca yazmaq olmaz).
                    err = str(e)
                    qid = re.search(r"'quotaId':\s*'([^']+)'", err)
                    qval = re.search(r"'quotaValue':\s*'(\d+)'", err)
                    if (qid and qval
                            and "Request" in qid.group(1)
                            and "PerDay" in qid.group(1)):
                        limit = int(qval.group(1))
                        _save_limit(model, limit)
                        db.set_usage_at_least(model, limit)
                logger.warning("Model %s işləmədi (%s), növbətiyə keçilir",
                               model, e.code)
                last_error = e
                continue
            raise
    raise last_error


def generate_post(topic: str | None = None,
                  avoid_ideas: list[str] | None = None) -> PostContent:
    """Azərbaycan dilində stat postu yaradır.

    topic — verilsə, stat bu mövzuda olur; verilməsə AI mövzu sütunlarından seçir.
    avoid_ideas — bu gün artıq işlənmiş mövzular (təkrarın qarşısını alır).
    """
    brand = _load_brand_profile()
    if topic:
        prompt = f"Bu mövzuda bir stat postu hazırla: {topic}"
    else:
        prompt = ("Brendin mövzu sütunlarından birini seç və bu gün üçün "
                  "təsirli bir stat postu hazırla.")
    if avoid_ideas:
        listed = "\n".join(f"- {i}" for i in avoid_ideas)
        prompt += ("\n\nBu gün artıq bu statlar hazırlanıb, onlardan həm mövzuca, "
                   f"həm bənzətməcə TAMAMİLƏ FƏRQLİ bir stat yaz:\n{listed}")
    return _generate(_system_prompt(brand), prompt)


def generate_chakra_post(chakra_name: str, chakra_hint: str,
                         avoid_ideas: list[str] | None = None) -> PostContent:
    """Konkret bir çakra haqqında maarifləndirici stat postu yaradır.

    Statda (quote) "çakra" sözü mütləq keçməlidir — şərt ödənməsə,
    bir neçə dəfə yenidən cəhd edilir.
    """
    brand = _load_brand_profile()
    prompt = f"""Bu gün üçün konkret bir ÇAKRA haqqında stat postu hazırla.

Çakra: {chakra_name}
Yeri və mahiyyəti: {chakra_hint}

Xüsusi tələblər:
- quote-da "çakra" sözü MÜTLƏQ keçməlidir (məsələn: "Kök çakran güclüdürsə,
  heç bir fırtına səni yıxa bilməz"). Söz hallanmış formada da ola bilər
  (çakran, çakrası).
- caption maarifləndirici olsun: bu çakranın adı, bədəndə yeri, nəyə cavabdeh
  olduğu və zəif/bağlı olanda insanın nə hiss etdiyi — 2-3 cümlə, sonda
  brendin tonunda yumşaq hərəkətə çağırış.
- Tibbi diaqnoz qoyma, müalicə vədi vermə."""
    if avoid_ideas:
        listed = "\n".join(f"- {i}" for i in avoid_ideas)
        prompt += ("\n\nBu gün artıq bu statlar hazırlanıb, onlardan həm mövzuca, "
                   f"həm bənzətməcə TAMAMİLƏ FƏRQLİ bir stat yaz:\n{listed}")
    content = None
    for attempt in range(3):
        content = _generate(_system_prompt(brand), prompt)
        if "çakra" in content.quote.lower():
            return content
        logger.warning("Çakra statında 'çakra' sözü yoxdur (cəhd %s): %s",
                       attempt + 1, content.quote)
    return content


def generate_russian_post(topic: str | None = None,
                          avoid_ideas: list[str] | None = None) -> PostContent:
    """Birbaşa rus dilində stat postu yaradır."""
    brand = _load_brand_profile()
    if topic:
        prompt = f"Bu mövzuda RUS DİLİNDƏ bir stat postu hazırla: {topic}"
    else:
        prompt = ("Brendin mövzu sütunlarından birini seç və RUS DİLİNDƏ "
                  "təsirli bir stat postu hazırla.")
    prompt += ("\n\nquote və caption RUS dilində olmalıdır. Stat rus dilində "
               "təbii və bədii səslənsin. idea '[RU] ' prefiksi ilə yazılsın.")
    if avoid_ideas:
        listed = "\n".join(f"- {i}" for i in avoid_ideas)
        prompt += f"\n\nBu statlardan fərqli mövzu və bənzətmə seç:\n{listed}"
    return _generate(_system_prompt(brand), prompt)


def make_russian_version(quotes: list[str]) -> PostContent:
    """Günün statlarından ən təsirlisini seçib rus dilində versiya hazırlayır."""
    brand = _load_brand_profile()
    listed = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(quotes))
    prompt = f"""Bu gün Azərbaycan dilində bu statlar hazırlanıb:

{listed}

Onlardan ƏN TƏSİRLİSİNİ seç və RUS DİLİNDƏ versiyasını hazırla:
- quote: statın rusca tərcüməsi — hərfi yox, bədii tərcümə; eyni dərinlik və
  ahəng rus dilində də hiss olunsun. Emojisiz, dırnaqsız.
- caption: rus dilində, brendin tonunda, 2-3 cümlə + hərəkətə çağırış. Hashtag yazma.
- idea: '[RU] ' prefiksi ilə seçdiyin statın qısa təsviri."""
    return _generate(_system_prompt(brand), prompt)
