#!/usr/bin/env python3
"""Apartment Hunter v2 — DEBUG MODE: Kufar API only, no LLM, no DDG."""

import os, sys, re, json, time
from datetime import datetime
from pathlib import Path
import requests

VERSION = "2.0-debug"
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
TARGET_QUOTA = 60
BATCH_DELAY = 0.5


def search_api():
    params = {
        "cat": 1010, "cur": "USD",
        "gtsy": "country-belarus~province-minsk~locality-minsk",
        "rms": "v.or:3,4", "size": 200, "sort": "lst.d", "typ": "sell",
    }
    resp = requests.get(
        "https://api.kufar.by/search-api/v2/search/map/over",
        params=params, headers=HEADERS, timeout=30,
    )
    data = resp.json()
    minsk = [a for a in data["ads"] if a.get("r") and a.get("p", 0) > 0]
    print(f"API: {data['total']} total, {len(minsk)} Minsk — will fetch up to {TARGET_QUOTA}")
    return minsk[:TARGET_QUOTA]


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
        graph = data.get("@graph", [data])
        for item in graph:
            if item.get("@type") != "Product":
                continue
            props = {p["name"]: p["value"] for p in item.get("additionalProperty", [])}
            price = float(item.get("offers", {}).get("price", 0))
            if price > MAX_PRICE:
                return {"skip": f"price {price}"}
            floor = props.get("Этаж", "?")
            tf = props.get("Количество этажей", "?")
            f = int(floor) if str(floor).isdigit() else 0
            ft = int(tf) if str(tf).isdigit() else 0
            if f == 1:
                return {"skip": "1st floor"}
            if ft == 5 and f in (4, 5):
                return {"skip": f"{f}/{ft}"}
            balc = props.get("Балкон", "Есть")
            if balc == "Нет":
                return {"skip": "no balcony"}
            return {
                "url": url, "price": price,
                "rooms": props.get("Количество комнат", "?"),
                "area": props.get("Общая площадь, м²", "?"),
                "floor": f"{floor}/{tf}",
                "balcony": balc,
                "material": props.get("Материал стен", "?"),
                "year": props.get("Год постройки", "?"),
                "address": item.get("address", {}).get("streetAddress", "?"),
                "district": props.get("Город / Район", "?"),
                "microdistrict": props.get("Микрорайон", "?"),
                "lat": ad["c"][1] if len(ad["c"]) > 1 else None,
                "lng": ad["c"][0] if len(ad["c"]) > 0 else None,
            }
        return None
    except Exception as e:
        return {"skip": str(e)}


def haversine(lat1, lng1, lat2, lng2):
    from math import radians, cos, sin, sqrt, asin
    r = 6371
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlng/2)**2
    return 2 * r * asin(sqrt(a))


def html_row(i, item):
    metro = min(TARGET_METRO, key=lambda m: haversine(item["lat"], item["lng"], m["lat"], m["lng"]))
    dist = round(haversine(item["lat"], item["lng"], metro["lat"], metro["lng"]), 1)
    return (
        f'<tr><td>{i}</td>'
        f'<td>{item["address"]}</td>'
        f'<td>{item["price"]:,.0f}</td>'
        f'<td>{item["rooms"]}</td>'
        f'<td>{item["area"]}</td>'
        f'<td>{item["floor"]}</td>'
        f'<td>{item["balcony"]}</td>'
        f'<td>{item["material"]}</td>'
        f'<td>{item["year"]}</td>'
        f'<td>м.{metro["name"]} ~{dist}км</td>'
        f'<td>{item["district"]}</td>'
        f'<td><a href="{item["url"]}" target="_blank">Куфар</a></td></tr>'
    )


def main():
    print(f"Apartment Hunter DEBUG {VERSION} — {datetime.now()}")
    print("[1] Kufar API...")
    ads = search_api()
    print(f"[2] Parsing {len(ads)} listings...")
    results, skipped = [], 0
    for i, ad in enumerate(ads):
        if i > 0:
            time.sleep(BATCH_DELAY)
        r = parse_one(ad)
        if r is None:
            continue
        if "skip" in r:
            skipped += 1
            continue
        results.append(r)
    print(f"[3] {len(results)} passed, {skipped} skipped")
    # Build HTML
    rows = "\n".join(html_row(i, item) for i, item in enumerate(results, 1))
    now = datetime.now()
    html = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<title>Minsk Apartments DEBUG {now:%d.%m.%Y}</title>
<style>body{{font-family:sans-serif;max-width:1100px;margin:1rem auto;padding:0 1rem}}
table{{border-collapse:collapse;font-size:14px}}th,td{{border:1px solid #ccc;padding:4px 6px;text-align:left}}
th{{background:#eee}}a{{color:#06c}}</style></head><body>
<h1>Minsk Apartments DEBUG</h1><p>{now:%d.%m.%Y %H:%M} UTC · {len(results)} вариантов · {len(ads)} собрано · {skipped} исключено</p>
<table><thead><tr><th>#</th><th>Адрес</th><th>Цена</th><th>Комн</th><th>м²</th><th>Этаж</th><th>Балкон</th><th>Материал</th><th>Год</th><th>Метро</th><th>Район</th><th>Ссылка</th></tr></thead>
<tbody>{rows}</tbody></table>
<p>DEBUG MODE — без LLM, без фильтра по 4-5/5, только Kufar. {now:%Y-%m-%d %H:%M}</p>
</body></html>"""
    idx = BASE_DIR / "index.html"
    idx.write_text(html, encoding="utf-8")
    print(f"OK: index.html ({len(html)} bytes)")


if __name__ == "__main__":
    main()