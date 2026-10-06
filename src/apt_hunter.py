#!/usr/bin/env python3
"""Apartment Hunter v2 — Kufar API + JSON-LD + LLM. No DDG for now."""

import os, re, json, time
from datetime import datetime
from pathlib import Path
import requests

VERSION = "2.0"
BASE_DIR = Path(__file__).resolve().parent.parent

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "x-segmentation": "routing=web_re;platform=web;application=ad_listing",
    "Referer": "https://re.kufar.by/",
}

TARGET_METRO = [
    {"name": "Восток", "lat": 53.9345, "lng": 27.5885},
    {"name": "Октябрьская", "lat": 53.9010, "lng": 27.5580},
    {"name": "Академия наук", "lat": 53.9200, "lng": 27.5980},
    {"name": "Якуба Коласа", "lat": 53.9150, "lng": 27.5810},
]

# Kufar metro station IDs from your search URL
# 3=Восток, 5=?, 7=Акад.наук?, 14=Октябрьская?, 16=Я.Коласа?, 17=?, 23=?
KUFAF_METRO_IDS = "v.or:7,16,23,3,17,14,5"

EXCLUDE_MICRO = ["минск-мир", "минск мир"]
EXCLUDE_ADDR = ["белинского", "беломорская"]  # scam / already seen

MAX_PRICE = 520000
# Don't need LLM/DS_API_KEY for raw table mode
LLM_MODEL = "deepseek-chat"  # kept for future use


def search_api():
    """Kufar API with metro + price + floor filters."""
    params = {
        "cat": 1010, "cur": "USD",
        "gtsy": "country-belarus~province-minsk~locality-minsk",
        "rms": "v.or:3,4",
        "mee": KUFAF_METRO_IDS,
        "nff": 1,
        "prc": "r:0,160000",
        "size": 100, "sort": "lst.d", "typ": "sell",
    }
    resp = requests.get("https://api.kufar.by/search-api/v2/search/map/over",
                       params=params, headers=HEADERS, timeout=30)
    data = resp.json()
    minsk = [a for a in data["ads"] if a.get("r") and a.get("p", 0) > 0]
    print(f"[Kufar] {data['total']} total, {len(minsk)} in zone")
    return minsk


def parse_one(ad):
    ad_id = ad["i"]
    url = f"https://re.kufar.by/vi/{ad_id}"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if r.status_code != 200:
            return None
        m = re.search(r'"application/ld\+json"[^>]*>(.*?)</script>', r.text, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(1))
        for item in data.get("@graph", [data]):
            item_type = item.get("@type", "")
            if isinstance(item_type, list):
                if "Product" not in item_type:
                    continue
            elif item_type != "Product":
                continue
            props = {p["name"]: p["value"] for p in item.get("additionalProperty", [])}
            price = float(item.get("offers", {}).get("price", 0))
            if price > MAX_PRICE:
                return {"skip": f"price>{MAX_PRICE}"}
            floor = props.get("Этаж", "?")
            tf = props.get("Количество этажей", "?")
            f = int(floor) if str(floor).isdigit() else 0
            ft = int(tf) if str(tf).isdigit() else 0
            if f == 1:
                return {"skip": "1fl"}
            if ft == 5 and f in (4, 5):
                return {"skip": f"{f}/5fl"}
            if props.get("Балкон", "") == "Нет":
                return {"skip": "no balcony"}
            # Exclude known scam/seen addresses
            addr_lower = item.get("address", {}).get("streetAddress", "").lower()
            if any(ex in addr_lower for ex in EXCLUDE_ADDR):
                return {"skip": "excluded addr"}
            return {
                "url": url, "price": price,
                "rooms": props.get("Количество комнат", "?"),
                "area": props.get("Общая площадь, м²", "?"),
                "area_living": props.get("Жилая площадь, м²", "?"),
                "floor": f"{floor}/{tf}",
                "balcony": props.get("Балкон", "—"),
                "material": props.get("Материал стен", "—"),
                "year": props.get("Год постройки", "—"),
                "address": item.get("address", {}).get("streetAddress", "?"),
                "district": props.get("Город / Район", "?"),
                "microdistrict": props.get("Микрорайон", "?"),
                "renovation": props.get("Ремонт", "?"),
                "lat": ad["c"][1] if len(ad["c"]) > 1 else None,
                "lng": ad["c"][0] if len(ad["c"]) > 0 else None,
            }
        return None
    except Exception as e:
        return {"skip": str(e)[:30]}


def haversine(lat1, lng1, lat2, lng2):
    from math import radians, cos, sin, sqrt, asin
    r = 6371
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlng/2)**2
    return 2 * r * asin(sqrt(a))


def call_llm(context: str, api_key: str) -> str:
    print(f"[LLM] Calling {LLM_MODEL}...")
    now = datetime.now()
    # Replace only {date}, escape other braces for LLM to fill
    system = SYSTEM_PROMPT.replace("{date}", now.strftime("%d.%m.%Y %H:%M Минск"))
    resp = requests.post(
        LLM_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": context},
            ],
            "temperature": 0.4, "max_tokens": 6000,
        },
        timeout=120,
    )
    if resp.status_code != 200:
        raise Exception(f"LLM API {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    print(f"[LLM] {usage.get('prompt_tokens','?')} in / {usage.get('completion_tokens','?')} out")
    return content


SYSTEM_PROMPT = """Ты — ассистент по поиску квартир. Данные уже отфильтрованы. Твоя задача — проранжировать и выдать HTML-таблицу.

ФОРМАТ — ТОЛЬКО HTML (без ```html```, без предисловий):

<p class="summary">Найдено N вариантов. {date}</p>

<table>
<thead><tr><th>#</th><th>Адрес</th><th>Цена</th><th>Комн</th><th>м²</th><th>м² жил</th><th>Этаж</th><th>Балкон</th><th>Материал</th><th>Год</th><th>Метро</th><th>Оценка</th><th>Ссылка</th></tr></thead>
<tbody>
<tr class="top3"><td>1</td><td>адрес</td><td class="price">цена</td><td>3</td><td>70</td><td>45</td><td>5/12</td><td>Лоджия</td><td>Кирпич</td><td>1995</td><td>м.Восток 0.8км</td><td><strong>7.5/10</strong></td><td><a href="URL" target="_blank">открыть</a></td></tr>
</tbody>
</table>

<div class="verdict"><h3>Рекомендации</h3><p>Топ-3 с аргументацией, 2 предложения на каждый.</p></div>
<div class="stats"><p>Собрано: {total}. После фильтрации: {filtered}. Исключено: {skipped}.</p></div>

CSS-классы: top3 (≥7), ok (5-6), low (<5). Сортируй по убыванию оценки. Максимум 15 строк. Не выдумывай данные."""


def score_item(r, dist):
    """Score 0-10. Higher = better."""
    s = 5.0
    # Metro (x10)
    if dist < 0.3: s += 2.5
    elif dist < 0.5: s += 2.0
    elif dist < 0.8: s += 1.5
    elif dist < 1.2: s += 1.0
    elif dist < 2.0: s += 0.5
    elif dist < 3.0: s += 0.0
    else: s -= 1.0

    # Price/m2 (x7)
    area = r.get("area", "0")
    try: area_f = float(area)
    except: area_f = 60
    ppm = r["price"] / max(area_f, 1)
    if ppm < 4500: s += 1.5
    elif ppm < 5000: s += 1.0
    elif ppm < 5500: s += 0.5
    elif ppm < 6500: s += 0.0
    else: s -= 0.5

    # Floor (x4)
    fl = r.get("floor", "?/?").split("/")
    try:
        f = int(fl[0]); tf = int(fl[1])
        if tf > 1:
            ratio = f / tf
            if 0.25 <= ratio <= 0.75: s += 0.5
            if f == tf: s -= 0.3
    except: pass

    # Material (x3)
    mat = r.get("material", "").lower()
    if "кирпич" in mat: s += 0.8
    elif "монолит" in mat: s += 0.5
    elif "каркас" in mat: s += 0.3
    elif "панел" in mat: s -= 0.2

    # Balcony (x2)
    balc = r.get("balcony", "").lower()
    if "два" in balc: s += 0.5
    elif "лоджи" in balc: s += 0.2

    # Area (x8)
    if area_f >= 80: s += 1.0
    elif area_f >= 70: s += 0.7
    elif area_f >= 60: s += 0.3

    # Year
    year = r.get("year", "0")
    try: y = int(year)
    except: y = 1980
    if y >= 2010: s += 0.5
    elif y >= 2000: s += 0.3
    elif y >= 1980: s += 0.0
    else: s -= 0.2

    # 4-room bonus
    if r.get("rooms") == "4": s += 0.3

    return round(min(10, max(0, s)), 1)


def main():
    now = datetime.now()
    print(f"Apartment Hunter v{VERSION} — {now}")

    ads = search_api()
    results, skipped = [], 0
    for i, ad in enumerate(ads):
        if i > 0:
            time.sleep(0.5)
        r = parse_one(ad)
        if r is None:
            continue
        if "skip" in r:
            skipped += 1
            continue
        micro = r.get("microdistrict", "").lower()
        if any(ex in micro for ex in EXCLUDE_MICRO):
            skipped += 1
            continue
        lat, lng = r["lat"], r["lng"]
        if lat and lng:
            metro = min(TARGET_METRO, key=lambda m: haversine(lat, lng, m["lat"], m["lng"]))
            dist = round(haversine(lat, lng, metro["lat"], metro["lng"]), 1)
        else:
            metro = {"name": "?"}
            dist = 99
        r["metro_name"] = metro["name"]
        r["metro_dist"] = dist
        r["score"] = score_item(r, dist)
        results.append(r)
    print(f"  {len(results)} passed, {skipped} skipped")

    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)

    # Always generate HTML
    rows = []
    for i, item in enumerate(results, 1):
        s = item["score"]
        cls = "top3" if s >= 6.5 else ("ok" if s >= 5 else "low")
        rows.append(
            f'<tr class="{cls}"><td>{i}</td><td>{item["address"]}</td>'
            f'<td class="price">{item["price"]:,.0f}</td>'
            f'<td>{item["rooms"]}</td><td>{item["area"]}</td><td>{item["area_living"]}</td>'
            f'<td>{item["floor"]}</td><td>{item["balcony"]}</td><td>{item["material"]}</td>'
            f'<td>{item["year"]}</td><td>м.{item["metro_name"]} {item["metro_dist"]}км</td>'
            f'<td><strong>{s}</strong></td>'
            f'<td><a href="{item["url"]}" target="_blank">Куфар</a></td></tr>'
        )

    body = (
        f'<p class="summary">Найдено {len(results)} вариантов · {len(ads)} собрано · {skipped} исключено</p>'
        f'<table><thead><tr>'
        f'<th>#</th><th>Адрес</th><th>Цена,BYN</th><th>к</th><th>м²</th><th>жил</th>'
        f'<th>Этаж</th><th>Балкон</th><th>Материал</th><th>Год</th>'
        f'<th>Метро</th><th>Рейтинг</th><th>Ссылка</th>'
        f'</tr></thead><tbody>{"".join(rows) if rows else "<tr><td colspan=12>Ничего не найдено</td></tr>"}'
        f'</tbody></table>'
    )

    # Build page
    html = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<title>Minsk Apartments — {now:%d.%m.%Y}</title>
<style>
:root{{--bg:#faf9f7;--text:#1a1a1a;--text2:#6b7280;--border:#e5e7eb;--accent:#2563eb;--green:#059669;--gold:#d97706}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:var(--bg);color:var(--text);line-height:1.6;font-size:15px;padding:1.5rem 1rem}}
.container{{max-width:1000px;margin:0 auto}}
header{{margin-bottom:1.5rem;padding-bottom:1rem;border-bottom:2px solid var(--accent)}}
header h1{{font-size:1.5rem;font-weight:700}}
header .meta{{margin-top:.3rem;font-size:.82rem;color:var(--text2)}}
header .criteria{{margin-top:.5rem;font-size:.78rem;color:var(--text2);line-height:1.5}}
.summary{{margin:.3rem 0 .8rem;font-size:.9rem;color:var(--text2)}}
table{{width:100%;border-collapse:collapse;margin:.5rem 0 1.5rem;font-size:.82rem}}
th{{background:#f3f4f6;text-align:left;padding:.5rem .4rem;font-weight:600;border-bottom:2px solid var(--border);white-space:nowrap}}
td{{padding:.45rem .4rem;border-bottom:1px solid var(--border)}}
tr.top3{{background:#ecfdf5}}tr.top3 td:first-child{{border-left:3px solid var(--green)}}
tr.ok{{background:#fffbeb}}tr.ok td:first-child{{border-left:3px solid var(--gold)}}
tr.low{{opacity:.65}}
.price{{white-space:nowrap;text-align:right}}
a{{color:var(--accent);text-decoration:underline;text-underline-offset:2px}}a:hover{{color:#1d4ed8}}
.verdict{{margin-top:1.5rem;padding:1rem 1.25rem;background:#f0f9ff;border-left:4px solid var(--accent);border-radius:4px}}
.verdict h3{{font-size:1rem;margin-bottom:.5rem}}.verdict p{{margin-bottom:.4rem;font-size:.88rem}}
.stats{{margin-top:.8rem;padding:.6rem .8rem;background:#f9fafb;border-radius:4px;font-size:.78rem;color:var(--text2)}}
footer{{margin-top:1.5rem;padding-top:1rem;border-top:1px solid var(--border);font-size:.75rem;color:var(--text2)}}
.disclaimer{{margin-top:.8rem;padding:.6rem .8rem;background:#fef2f2;border-left:3px solid #ef4444;border-radius:4px;font-size:.78rem;color:#991b1b}}
</style></head><body><div class="container">
<header><h1>Minsk Apartments</h1>
<div class="meta">{now.day} {["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"][now.month-1]} {now.year} · {now:%H:%M} Минск</div></header>
<main>{body}</main>
<div class="disclaimer">Авто-сбор из Kufar API. Проверяйте на сайте перед звонком.</div>
<footer><p>Apartment Hunter v{VERSION} · {now:%d.%m.%Y %H:%M} Минск</p></footer>
</div></body></html>"""

    idx = BASE_DIR / "index.html"
    idx.write_text(html, encoding="utf-8")
    print(f"index.html ({len(html)} bytes) saved")


if __name__ == "__main__":
    main()