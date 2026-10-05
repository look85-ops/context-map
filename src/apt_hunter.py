#!/usr/bin/env python3
"""Apartment Hunter v2 — Kufar API + JSON-LD + LLM. No DDG for now."""

import os, sys, re, json, time
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

MAX_PRICE = 520000
LLM_MODEL = "deepseek-chat"
LLM_URL = "https://openai.bothub.ru/v1/chat/completions"


def search_api():
    params = {"cat": 1010, "cur": "USD", "gtsy": "country-belarus~province-minsk~locality-minsk",
              "rms": "v.or:3,4", "size": 200, "sort": "lst.d", "typ": "sell"}
    resp = requests.get("https://api.kufar.by/search-api/v2/search/map/over",
                       params=params, headers=HEADERS, timeout=30)
    data = resp.json()
    minsk = [a for a in data["ads"] if a.get("r") and a.get("p", 0) > 0]
    print(f"[Kufar] {data['total']} total, {len(minsk)} Minsk")
    return minsk[:60]


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
            if item.get("@type") != "Product":
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
            return {
                "url": url, "price": price,
                "rooms": props.get("Количество комнат", "?"),
                "area": props.get("Общая площадь", "?"),
                "area_living": props.get("Жилая площадь", "?"),
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
    resp = requests.post(
        LLM_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
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


def main():
    now = datetime.now()
    print(f"Apartment Hunter v{VERSION} — {now}")

    api_key = os.environ.get("DS_API_KEY") or os.environ.get("GH_TOKEN") or ""
    if not api_key:
        print("FATAL: no API key")
        return

    # Phase 1-2: Kufar
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
        # Score
        metro = min(TARGET_METRO, key=lambda m: haversine(r["lat"], r["lng"], m["lat"], m["lng"]))
        dist = round(haversine(r["lat"], r["lng"], metro["lat"], metro["lng"]), 1)
        r["metro_name"] = metro["name"]
        r["metro_dist"] = dist
        results.append(r)
    print(f"  {len(results)} passed, {skipped} skipped")

    if not results:
        print("Nothing found")
        return

    # Build context
    lines = ["## ОБЪЯВЛЕНИЯ KUFAR (проверены, детали из JSON-LD)\n"]
    for i, item in enumerate(results, 1):
        lines.append(
            f"[{i}] {item['address']} | {item['price']:,.0f} BYN | "
            f"{item['rooms']}к | {item['area']}м²({item['area_living']}жил) | "
            f"{item['floor']}эт | балкон:{item['balcony']} | {item['material']} | "
            f"{item['year']}г | {item['district']} | м.{item['metro_name']} ~{item['metro_dist']}км | "
            f"ремонт:{item['renovation']}"
        )
        lines.append(f"   URL: {item['url']}")

    # Phase 3: LLM
    print(f"[LLM] {len(results)} listings, context {sum(len(l) for l in lines)} chars")
    context = "\n".join(lines)
    try:
        raw = call_llm(context, api_key)
    except Exception as e:
        print(f"LLM FAIL: {e}")
        # Fallback: plain HTML table
        rows = []
        for i, item in enumerate(results, 1):
            rows.append(
                f'<tr><td>{i}</td><td>{item["address"]}</td><td class="price">{item["price"]:,.0f}</td>'
                f'<td>{item["rooms"]}</td><td>{item["area"]}</td><td>{item["area_living"]}</td>'
                f'<td>{item["floor"]}</td><td>{item["balcony"]}</td><td>{item["material"]}</td>'
                f'<td>{item["year"]}</td><td>м.{item["metro_name"]} {item["metro_dist"]}км</td>'
                f'<td>—</td><td><a href="{item["url"]}" target="_blank">открыть</a></td></tr>'
            )
        body = (
            f'<p class="summary">Найдено {len(results)} (LLM недоступен — сырая таблица)</p>'
            f'<table><thead><tr><th>#</th><th>Адрес</th><th>Цена</th><th>Комн</th><th>м²</th><th>жил</th>'
            f'<th>Этаж</th><th>Балкон</th><th>Материал</th><th>Год</th><th>Метро</th><th>Оценка</th><th>Ссылка</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table>'
        )
    else:
        body = raw.strip()
        if body.startswith("```"):
            nl = body.find("\n") + 1
            le = body.rfind("```")
            body = body[nl:le].strip() if le > nl else body

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
<div class="meta">{now.day} {["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"][now.month-1]} {now.year} · Kufar API + DeepSeek · 2×/день</div>
<div class="criteria">3-4 комнаты · до 520 000 BYN · не 1-й эт · не 4-5/5 · балкон/лоджия · м.Восток — м.Октябрьская</div></header>
<main>{body}</main>
<div class="disclaimer">Авто-сбор из Kufar API. Проверяйте на сайте перед звонком.</div>
<footer><p>Apartment Hunter v{VERSION} · {now:%d.%m.%Y %H:%M} Минск</p></footer>
</div></body></html>"""

    idx = BASE_DIR / "index.html"
    idx.write_text(html, encoding="utf-8")
    print(f"index.html ({len(html)} bytes) saved")


if __name__ == "__main__":
    main()