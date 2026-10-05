#!/usr/bin/env python3
"""
Apartment Hunter v2 — авто-подбор квартир в Минске через API Kufar + Realt (DDG).
Kufar API → JSON-LD парсинг → фильтр по критериям → LLM-ранжирование → HTML.
Запуск: GitHub Actions 2×/день (9:00 и 19:00 Минск = 6:00 и 16:00 UTC).
"""

import os
import sys
import re
import json
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import requests
from ddgs import DDGS
import markdown as md_lib

VERSION = "2.0"

API_KEY = os.environ.get("DS_API_KEY", os.environ.get("GH_TOKEN", ""))
if not API_KEY:
    print("FATAL: DS_API_KEY or GH_TOKEN not set")
    sys.exit(1)

BASE_URL = "https://openai.bothub.ru/v1"
FALLBACK_URL = "https://models.inference.ai.azure.com"
MODEL = "deepseek-chat"
FALLBACK_MODEL = "Meta-Llama-3.3-70B-Instruct"

BASE_DIR = Path(__file__).resolve().parent.parent

KUFAR_SEARCH_URL = "https://api.kufar.by/search-api/v2/search/map/over"
KUFAR_LISTING_URL = "https://re.kufar.by/vi/{}"

CRITERIA = {
    "max_price_byn": 520000,
    "rooms": [3, 4],
    "no_first_floor": True,
    "no_4_5_in_5floor": True,
    "balcony_required": True,
}

# Целевые координаты (м.Восток: 53.9345,27.5885; м.Октябрьская: 53.9010,27.5580)
TARGET_METRO = [
    {"name": "Восток", "lat": 53.9345, "lng": 27.5885},
    {"name": "Октябрьская", "lat": 53.9010, "lng": 27.5580},
    {"name": "Академия наук", "lat": 53.9200, "lng": 27.5980},
    {"name": "Якуба Коласа", "lat": 53.9150, "lng": 27.5810},
]

# Realt/DDG queries — дополнительный источник
REALT_QUERIES = [
    '3 комнатная квартира купить Минск Восток Октябрьская site:realt.by',
    '3-комнатная квартира купить Минск site:realt.by',
    '4-комнатная квартира купить Минск site:realt.by',
]

SYSTEM_PROMPT = """Ты — ассистент по поиску квартир в Минске. Анализируешь реальные объявления.

КРИТЕРИИ Наташи (уже отфильтрованы в данных):
- 3 или 4 комнаты
- Цена: до 520 000 BYN
- НЕ первый этаж
- НЕ 4-й и НЕ 5-й этаж в пятиэтажках
- Балкон или лоджия обязателен
- Целевая зона: м.Восток — м.Октябрьская

ТВОЯ ЗАДАЧА:
1. Проверить каждое объявление на соответствие критериям (вдруг фильтр пропустил)
2. Проранжировать по убыванию качества
3. Сформировать HTML-таблицу

ВЕСА:
- Близость к метро ×10
- Цена/м² ×8
- Этаж (средние > крайние) ×4
- Кирпич/монолит > панель ×3
- Балкон (два > один > лоджия) ×2

ФОРМАТ ВЫВОДА — HTML (без ```html```, без предисловий):

<p class="summary">Найдено N вариантов. Обновлено: {date_full}</p>

<table>
<thead><tr>
  <th>#</th><th>Адрес</th><th>Цена, BYN</th><th>Комн</th><th>м²</th>
  <th>м² жил</th><th>Этаж</th><th>Балкон</th><th>Материал</th><th>Год</th>
  <th>Метро</th><th>Оценка</th><th>Ссылка</th>
</tr></thead>
<tbody>
<!-- каждый вариант: -->
<tr class="top3|ok|low">
  <td>{rank}</td>
  <td>{address_short}</td>
  <td class="price">{price_formatted}</td>
  <td>{rooms}</td>
  <td>{area_total}</td>
  <td>{area_living}</td>
  <td>{floor} / {total_floors}</td>
  <td>{balcony}</td>
  <td>{material}</td>
  <td>{year}</td>
  <td>{nearest_metro}</td>
  <td><strong>{score}/10</strong></td>
  <td><a href="{url}" target="_blank">открыть</a></td>
</tr>
</tbody>
</table>

<div class="verdict"><h3>Рекомендации</h3>
<p>Топ-3 для просмотра (с аргументацией — 2 предложения на каждый).</p>
<p>На что обратить внимание: риски, подозрительные моменты.</p>
</div>

<div class="stats">
  <p>Собрано: {total_collected} · После фильтрации: {filtered} · Исключено: {skipped} (не Минск/1-й этаж/4-5 этаж в пятиэтажке/без балкона)</p>
</div>

ПРАВИЛА:
- НЕ выдумывай данные. Только то, что во входных данных.
- Все URL должны быть из входных данных.
- CSS-класс: top3 (оценка ≥7), ok (5-6), low (<5).
- Сортируй по убыванию оценки. Максимум 15 строк.
- Если данных нет — оставь «—» в ячейке."""  # noqa: E501


def kufar_search() -> list[dict]:
    """Get ad IDs from Kufar API. Price filter in parse_listing, not API."""
    params = {
        "cat": 1010,
        "cur": "USD",
        "gtsy": "country-belarus~province-minsk~locality-minsk",
        "rms": "v.or:3,4",
        "size": 200,
        "sort": "lst.d",
        "typ": "sell",
    }
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "x-segmentation": "routing=web_re;platform=web;application=ad_listing",
        "Referer": "https://re.kufar.by/",
    }
    try:
        resp = requests.get(KUFAR_SEARCH_URL, params=params, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            print(f"Kufar API error: {resp.status_code}")
            return []
        data = resp.json()
        ads = data.get("ads", [])
        total = data.get("total", 0)
        # Only Minsk (r=true) and price > 0
        minsk_ads = [a for a in ads if a.get("r") and a.get("p", 0) > 0]
        print(f"[Kufar] {total} total, {len(minsk_ads)} in Minsk")
        return minsk_ads
    except Exception as e:
        print(f"Kufar search error: {e}")
        return []


def parse_listing(ad: dict) -> dict | None:
    """Fetch individual listing page, extract JSON-LD."""
    ad_id = ad["i"]
    url = f"https://re.kufar.by/vi/{ad_id}"
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "ApartmentHunter/2.0"},
            timeout=15,
        )
        if resp.status_code != 200:
            return None

        # Extract JSON-LD (Next.js dynamic script — type attr in non-standard position)
        match = re.search(
            r'"application/ld\+json"[^>]*>(.*?)</script>',
            resp.text,
            re.DOTALL,
        )
        if not match:
            return None

        data = json.loads(match.group(1))
        graph = data.get("@graph", [data])
        product = None
        for item in graph:
            if item.get("@type") == "Product":
                product = item
                break
        if not product:
            return None

        # Extract fields
        props = {}
        for prop in product.get("additionalProperty", []):
            props[prop["name"]] = prop["value"]

        def get_prop(*names):
            for n in names:
                if n in props:
                    return props[n]
            return "—"

        rooms = int(get_prop("Количество комнат"))
        area_total = float(get_prop("Общая площадь, м²"))
        area_living = get_prop("Жилая площадь, м²")
        floor = get_prop("Этаж")
        total_floors = get_prop("Количество этажей")
        balcony = get_prop("Балкон")
        material = get_prop("Материал стен")
        year = get_prop("Год постройки")
        address = product.get("address", {}).get("streetAddress", "—")
        district = get_prop("Город / Район")
        microdistrict = get_prop("Микрорайон")
        renovation = get_prop("Ремонт")

        offer = product.get("offers", {})
        price_byn = float(offer.get("price", 0))

        # Hard filters
        if price_byn > CRITERIA["max_price_byn"]:
            return {"_skip": f"цена {price_byn:,.0f} > {CRITERIA['max_price_byn']:,}"}

        f = int(floor) if floor.isdigit() else 0
        tf = int(total_floors) if total_floors.isdigit() else 0

        if CRITERIA["no_first_floor"] and f == 1:
            return {"_skip": "1-й этаж"}
        if CRITERIA["no_4_5_in_5floor"] and tf == 5 and f in (4, 5):
            return {"_skip": f"{f} этаж в пятиэтажке"}
        if CRITERIA["balcony_required"] and balcony == "Нет":
            return {"_skip": "без балкона"}

        return {
            "url": url,
            "ad_id": ad_id,
            "price_byn": price_byn,
            "rooms": rooms,
            "area_total": area_total,
            "area_living": area_living,
            "floor": floor,
            "total_floors": total_floors,
            "balcony": balcony,
            "material": material,
            "year": year,
            "address": address,
            "district": district,
            "microdistrict": microdistrict,
            "renovation": renovation,
            "lat": ad["c"][1] if len(ad["c"]) > 1 else None,
            "lng": ad["c"][0] if len(ad["c"]) > 0 else None,
        }
    except Exception as e:
        print(f"  Parse error {ad_id}: {e}")
        return None


def compute_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance in km."""
    from math import radians, cos, sin, sqrt, asin
    r = 6371
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * r * asin(sqrt(a))


def find_nearest_metro(lat: float, lng: float) -> tuple[str, float]:
    """Return (name, distance_km) of nearest metro."""
    if lat is None or lng is None:
        return "—", 99.0
    best = min(
        TARGET_METRO,
        key=lambda m: compute_distance(lat, lng, m["lat"], m["lng"]),
    )
    d = compute_distance(lat, lng, best["lat"], best["lng"])
    return best["name"], round(d, 1)


def score_listing(item: dict, metro_dist: float) -> float:
    """Score 0-10."""
    score = 5.0  # baseline

    # Metro distance — closer is better
    if metro_dist < 0.5:
        score += 2.0
    elif metro_dist < 1.0:
        score += 1.5
    elif metro_dist < 1.5:
        score += 1.0
    elif metro_dist < 2.0:
        score += 0.5
    else:
        score -= 0.5

    # Price per m²
    ppm = item["price_byn"] / max(item["area_total"], 1)
    if ppm < 4500:
        score += 1.5
    elif ppm < 5500:
        score += 1.0
    elif ppm < 6500:
        score += 0.5

    # Floor
    f = int(item["floor"]) if str(item["floor"]).isdigit() else 5
    tf = int(item["total_floors"]) if str(item["total_floors"]).isdigit() else 9
    if tf > 1:
        ratio = f / tf
        if 0.3 <= ratio <= 0.7:
            score += 0.5
        if f == tf:
            score -= 0.3

    # Material
    mat = item["material"].lower()
    if "кирпич" in mat:
        score += 0.5
    elif "монолит" in mat:
        score += 0.3
    elif "панел" in mat:
        score -= 0.3

    # Balcony
    balc = item["balcony"].lower()
    if "два" in balc:
        score += 0.5
    elif "лоджи" in balc:
        score += 0.2

    # Area
    if item["area_total"] >= 75:
        score += 0.5
    elif item["area_total"] >= 65:
        score += 0.3

    return min(10, max(0, score))


def search_realt_ddg() -> list[dict]:
    """Backup: search Realt.by via DDG."""
    results = []
    with DDGS() as ddgs:
        for query in REALT_QUERIES:
            try:
                for r in ddgs.text(query, max_results=3):
                    url = r.get("href", "")
                    if "realt.by" in url and url not in {x["url"] for x in results}:
                        results.append({
                            "url": url,
                            "title": r.get("title", ""),
                            "snippet": r.get("body", ""),
                            "source": "realt",
                        })
            except Exception as e:
                print(f"DDG Realt fail: {e}")
    print(f"[Realt/DDG] {len(results)} listings found")
    return results


def build_context(kufar_listings: list[dict], realt_listings: list[dict]) -> str:
    """Build context for LLM."""
    lines = ["## KUFAR (проверенные, с деталями)\n"]

    for i, item in enumerate(kufar_listings, 1):
        metro_name, metro_dist = find_nearest_metro(
            item.get("lat"), item.get("lng"),
        )
        score = score_listing(item, metro_dist)
        price_fmt = f"{int(item['price_byn']):,}".replace(",", " ")
        addr = item["address"]

        lines.append(
            f"[KF{i}] {addr} | {price_fmt} BYN | "
            f"{item['rooms']}к | {item['area_total']}м²({item['area_living']}жил) | "
            f"{item['floor']}/{item['total_floors']}эт | "
            f"балкон:{item['balcony']} | {item['material']} | "
            f"{item['year']}г | {item['district']} | {item['microdistrict']} | "
            f"м.{metro_name} ~{metro_dist}км | ремонт:{item['renovation']} | "
            f"score:{score:.1f}"
        )
        lines.append(f"   URL: {item['url']}")

    if kufar_listings:
        lines.append("")

    if realt_listings:
        lines.append("## REALT.BY (сниппеты — детали проверять на сайте)\n")
        for i, r in enumerate(realt_listings, 1):
            lines.append(f"[RT{i}] {r['title']}")
            lines.append(f"   URL: {r['url']}")
            lines.append(f"   {r['snippet'][:200]}")
            lines.append("")

    lines.append("\n---")
    lines.append(f"Kufar API: {len(kufar_listings)} | Realt DDG: {len(realt_listings)}")
    return "\n".join(lines)


def call_llm(context: str) -> str:
    """Send context to LLM, get HTML table back."""
    now = datetime.now()
    date_full = now.strftime("%d.%m.%Y %H:%M Минск")
    system = SYSTEM_PROMPT.format(date_full=date_full)
    gh_key = os.environ.get("GH_TOKEN", "")

    endpoints = [
        {"url": f"{BASE_URL}/chat/completions", "key": API_KEY, "model": MODEL},
    ]
    if gh_key:
        endpoints.append({"url": f"{FALLBACK_URL}/chat/completions", "key": gh_key, "model": FALLBACK_MODEL})

    last_error = None
    for ep in endpoints:
        try:
            resp = requests.post(
                ep["url"],
                headers={
                    "Authorization": f"Bearer {ep['key']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": ep["model"],
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": context},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 8000,
                },
                timeout=180,
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                print(f"LLM ({ep['model']}): {usage.get('prompt_tokens','?')} in / {usage.get('completion_tokens','?')} out")
                return content
            last_error = f"API {resp.status_code}"
            print(f"  {ep['model']}: {last_error}")
        except Exception as e:
            last_error = str(e)
            print(f"  {ep['model']}: {last_error}")

    raise Exception(f"All APIs failed: {last_error}")


def extract_html(raw: str) -> str:
    """Strip code fences from LLM output."""
    raw = raw.strip()
    if raw.startswith("```"):
        first = raw.find("\n") + 1 if "\n" in raw else 3
        last = raw.rfind("```")
        if last > first:
            raw = raw[first:last].strip()
    return raw


def build_page(body_html: str, total_kufar: int, total_realt: int) -> str:
    """Wrap HTML body into full page."""
    now = datetime.now()
    months = [
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    ]
    date_ru = f"{now.day} {months[now.month - 1]} {now.year}"
    gen_ts = now.strftime("%d.%m.%Y %H:%M Минск")
    total = total_kufar + total_realt

    body_html = body_html.replace('<a href="', '<a target="_blank" rel="noopener" href="')

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Minsk Apartments — {now.strftime('%d.%m.%Y')}</title>
<style>
:root {{--bg:#faf9f7;--text:#1a1a1a;--text2:#6b7280;--border:#e5e7eb;--accent:#2563eb;--green:#059669;--gold:#d97706;--red:#dc2626;--w:1000px}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--text);line-height:1.6;font-size:15px;padding:1.5rem 1rem}}
.container{{max-width:var(--w);margin:0 auto}}
header{{margin-bottom:1.5rem;padding-bottom:1rem;border-bottom:2px solid var(--accent)}}
header h1{{font-size:1.5rem;font-weight:700}}
header .meta{{margin-top:0.3rem;font-size:0.82rem;color:var(--text2)}}
header .criteria{{margin-top:0.5rem;font-size:0.78rem;color:var(--text2);line-height:1.5}}
.summary{{margin:0.3rem 0 0.8rem;font-size:0.9rem;color:var(--text2)}}
table{{width:100%;border-collapse:collapse;margin:0.5rem 0 1.5rem;font-size:0.82rem}}
th{{background:#f3f4f6;text-align:left;padding:0.5rem 0.4rem;font-weight:600;border-bottom:2px solid var(--border);white-space:nowrap}}
td{{padding:0.45rem 0.4rem;border-bottom:1px solid var(--border);vertical-align:top}}
tr.top3{{background:#ecfdf5}}tr.top3 td:first-child{{border-left:3px solid var(--green)}}
tr.ok{{background:#fffbeb}}tr.ok td:first-child{{border-left:3px solid var(--gold)}}
tr.low{{opacity:0.65}}
.price{{white-space:nowrap;text-align:right}}
a{{color:var(--accent);text-decoration:underline;text-underline-offset:2px}}a:hover{{color:#1d4ed8}}
.verdict{{margin-top:1.5rem;padding:1rem 1.25rem;background:#f0f9ff;border-left:4px solid var(--accent);border-radius:4px}}
.verdict h3{{font-size:1rem;margin-bottom:0.5rem}}
.verdict p{{margin-bottom:0.4rem;font-size:0.88rem}}
.stats{{margin-top:0.8rem;padding:0.6rem 0.8rem;background:#f9fafb;border-radius:4px;font-size:0.78rem;color:var(--text2)}}
footer{{margin-top:1.5rem;padding-top:1rem;border-top:1px solid var(--border);font-size:0.75rem;color:var(--text2)}}
.disclaimer{{margin-top:0.8rem;padding:0.6rem 0.8rem;background:#fef2f2;border-left:3px solid #ef4444;border-radius:4px;font-size:0.78rem;color:#991b1b}}
@media(max-width:800px){{table{{font-size:0.72rem}}th,td{{padding:0.35rem 0.25rem}}}}
</style>
</head>
<body>
<div class="container">
<header>
  <h1>Minsk Apartments</h1>
  <div class="meta">{date_ru} · авто-подбор 2×/день · м.Восток — м.Октябрьская</div>
  <div class="criteria">3-4 комнаты · до 520 000 BYN · не 1-й эт · не 4-5/5 · балкон/лоджия · Kufar API + Realt.by (DDG)</div>
</header>
<main>
{body_html}
</main>
<div class="disclaimer">
  <strong>Важно:</strong> Данные из API Kufar.by и поисковых сниппетов Realt.by. Проверяйте цену, этаж и балкон на сайте объявления перед звонком. Возможны скам-объявления.
</div>
<footer>
  <p>Apartment Hunter v{VERSION} · {total} источников · {gen_ts}</p>
  <p><a href="https://github.com/look85-ops/context-map">look85-ops/context-map</a></p>
</footer>
</div>
</body>
</html>"""


def save(html: str):
    date_str = datetime.now().strftime("%Y-%m-%d_%H%M")
    idx = BASE_DIR / "index.html"
    idx.write_text(html, encoding="utf-8")
    print(f"index.html ({len(html)} bytes)")
    ad = BASE_DIR / "artifacts"
    ad.mkdir(exist_ok=True)
    (ad / f"hunt_{date_str}.html").write_text(html, encoding="utf-8")


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"Apartment Hunter v{VERSION} — {now}")

    # Phase 1: Kufar API
    print("\n[Phase 1] Kufar API search...")
    ads = kufar_search()
    if not ads:
        print("No Kufar ads found")

    # Phase 2: Fetch listing details (sequential, 0.5s delay to respect rate limit)
    batch = ads[:60]
    print(f"\n[Phase 2] Fetching details for {len(batch)} listings...")
    kufar_listings = []
    skipped = 0

    for i, ad in enumerate(batch):
        if i > 0:
            time.sleep(0.5)
        result = parse_listing(ad)
        if result is None:
            continue
        if "_skip" in result:
            skipped += 1
            continue
        metro_name, metro_dist = find_nearest_metro(
            result.get("lat"), result.get("lng"),
        )
        result["metro_name"] = metro_name
        result["metro_dist"] = metro_dist
        result["score"] = score_listing(result, metro_dist)
        kufar_listings.append(result)
        if len(kufar_listings) % 10 == 0:
            print(f"  ... {len(kufar_listings)} parsed, {skipped} skipped")

    # Sort by score
    kufar_listings.sort(key=lambda x: x["score"], reverse=True)
    print(f"  Kufar: {len(kufar_listings)} passed, {skipped} skipped")

    # Phase 3: Realt.by via DDG
    print("\n[Phase 3] Realt.by DDG search...")
    realt_listings = search_realt_ddg()

    if not kufar_listings and not realt_listings:
        print("Nothing found, saving empty page")
        save(build_page('<div class="summary">Ничего не найдено.</div>', 0, 0))
        return

    # Phase 4: LLM analysis
    print(f"\n[Phase 4] LLM analysis ({len(kufar_listings)} Kufar + {len(realt_listings)} Realt)...")
    context = build_context(kufar_listings, realt_listings)
    raw = call_llm(context)
    body = extract_html(raw)

    html = build_page(body, len(kufar_listings), len(realt_listings))
    save(html)
    print(f"\n[Done] Apartment Hunter v{VERSION}")


if __name__ == "__main__":
    main()