#!/usr/bin/env python3
"""
Context Map — geopolitical digest for relocation decisions.
Searches news, summarizes via DeepSeek V3 (bothub.ru), generates HTML.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from ddgs import DDGS
import markdown as md_lib

API_KEY = os.environ.get("DS_API_KEY", os.environ.get("GH_TOKEN", ""))
if not API_KEY:
    print("FATAL: DS_API_KEY or GH_TOKEN not set")
    sys.exit(1)

BASE_URL = "https://openai.bothub.ru/v1"
FALLBACK_URL = "https://models.inference.ai.azure.com"
MODEL = "deepseek-chat"
FALLBACK_MODEL = "Meta-Llama-3.3-70B-Instruct"

BASE_DIR = Path(__file__).resolve().parent.parent

SOURCE_BLOCKLIST = [
    "ria.ru", "tass.ru", "rt.com", "ukraina.ru", "life.ru",
    "kremlin.ru", "sputnik", "news-front", "rusvesna",
    "pravda.ru", "rublacklist", "mil.ru", "function.mil.ru",
    "censor.net", "patrioty.org.ua", "ukrinform.ua",
    "vz.ru", "iz.ru", "rg.ru", "1tv.ru", "russia.tv",
    "vesti.ru", "gov.ru", "mid.ru",
]

SEARCH_QUERIES = [
    "Россия Украина война новости 2026",
    "экономика Россия санкции 2026",
    "курс рубля доллар евро 2026",
    "Беларусь экономика новости 2026",
    "Минск недвижимость цены 2026",
    "работа Беларусь IT вакансии 2026",
    "Украина война экономика 2026",
    "нефть цены геополитика 2026",
    "санкции Европа США Россия 2026",
    "релокация Беларусь из России 2026",
]

SYSTEM_PROMPT = """Ты — аналитический ассистент Context Map. Составляешь дайджест для Наташи, планирующей переезд в Минск из РФ. Наташа — L&D специалист (не программист), поэтому объясняй экономические термины встроенно, без сносок.

Формат: Markdown. Дата: {date}

СТРУКТУРА ДАЙДЖЕСТА (строго соблюдай):

# Context Map — Дайджест {date}

## 1. Обзорная карта
Ключевой тренд. Главный риск. Главная возможность. (2-3 абзаца, связанных с переездом)

## 2. Поле боя
### РФ (санкции, экономика, курс рубля — только что влияет на жизнь)
### РБ (работа, недвижимость, экономика, визы — фокус на переезд)
### Украина (ход войны, экономика — косвенные эффекты)
### Мир (нефть, ставки, геополитика)

## 3. Слабые сигналы
3-5 edge signals — неочевидное, что может изменить расклад

## 4. Устойчивые паттерны
Что подтверждается 3+ периодов подряд

## 5. Влияние на решения (важнейший раздел — пиши развёрнуто, с цифрами и конкретикой)
### Работа: з/п в Минске по твоему профилю (L&D/edTech, не чистый IT), тренды найма, удалёнка vs офис
### Недвижимость: цены/аренда в Минске, ипотека, прогноз на квартал
### Деньги: какой валюте/инструменту доверять, инфляция, лимиты переводов
### Отрасли: что растёт (IT/edTech/АПК) и что угасает (нефтегаз/логистика РФ) — влияние на карьеру

## 6. Сценарии на 1-3 мес
3 варианта: базовый / эскалация / деэскалация. К каждому — триггеры и влияние на переезд

## 7. Дополнительно
Слабый сигнал или слепое пятно, которое стоит отследить

---

ФОРМАТ КАЖДОЙ ССЫЛКИ (ЭТО ОБЯЗАТЕЛЬНО):
Каждый источник — ТОЛЬКО [Название](полный URL). 
Правильно: «Курс рубля — 89/$ [RBC](https://www.rbc.ru/...)»
Неправильно: «Курс рубля — 89/$ (RBC)» или «Курс рубля — 89/$ [1]»
В конце дайджеста — блок "Источники:" со всеми URL в формате [N](url)

ОБЩИЕ ПРАВИЛА:
- Лаконично: макс 3 абзаца на раздел
- Без воды: никаких "важно отметить", "следует подчеркнуть"
- Нет данных — прочерк (—)
- Тон: спокойный, аналитический, ноль паники и хайпа"""


def is_blocked(url: str) -> bool:
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower()
    for blocked in SOURCE_BLOCKLIST:
        if blocked in domain:
            return True
    return False


def search_news() -> list[dict]:
    seen = set()
    results = []
    with DDGS() as ddgs:
        for query in SEARCH_QUERIES:
            try:
                for r in ddgs.text(query, max_results=3):
                    url = r.get("href", "")
                    if url and url not in seen and not is_blocked(url):
                        seen.add(url)
                        results.append({
                            "title": r.get("title", ""),
                            "snippet": r.get("body", ""),
                            "url": url,
                        })
            except Exception as e:
                print(f"Search fail '{query}': {e}")
    print(f"Collected {len(results)} unique items (blocklist filtered)")
    return results


def build_context(results: list[dict]) -> str:
    lines = ["## Новости за 3 дня\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] {r['title']}")
        lines.append(f"{r['snippet']}\n")

    lines.append("\n---\n")
    lines.append("## ИСТОЧНИКИ ДЛЯ ЦИТИРОВАНИЯ (используй ТОЛЬКО эти URL):\n")
    for i, r in enumerate(results, 1):
        title_short = r['title'][:60]
        lines.append(f"{i}. {r['url']} — {title_short}")

    return "\n".join(lines)


def call_llm(context: str) -> str:
    today = datetime.now().strftime("%d.%m.%Y")
    system = SYSTEM_PROMPT.format(date=today)
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
                    "temperature": 0.7,
                    "max_tokens": 16000,
                },
                timeout=180,
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                model_used = ep["model"]
                print(f"LLM ({model_used}): {usage.get('prompt_tokens','?')} in / {usage.get('completion_tokens','?')} out")
                return content
            last_error = f"API {resp.status_code}"
            print(f"  {ep['model']}: {last_error}, trying next...")
        except Exception as e:
            last_error = str(e)
            print(f"  {ep['model']}: {last_error}, trying next...")

    raise Exception(f"All APIs failed: {last_error}")


def post_process_md(md: str) -> str:
    """Fix common LLM output issues."""
    import re

    # Strip code fence if LLM wrapped entire output in triple backticks
    md = md.strip()
    if md.startswith("```"):
        first = md.find("\n") + 1 if "\n" in md else 3
        last = md.rfind("```")
        md = md[first:last].strip()

    # Fix section headings
    md = md.replace("Что я могла упустить", "Дополнительно")
    md = md.replace("Что я упустила", "Дополнительно")
    md = md.replace("Что можно упустить", "Дополнительно")

    bare_refs = re.findall(r'\[\d+\]', md)
    if bare_refs:
        print(f"WARNING: {len(bare_refs)} bare [N] refs stripped")
        md = re.sub(r'\[\d+\]', '', md)

    # Normalize number format: comma → thin space in numbers (Russian style)
    md = re.sub(r'(?<=\d),(?=\d{3})', '\u2009', md)

    # Make sources block readable: [N]. url → [N]. [domain](url)
    def linkify_url(match):
        num = match.group(1)
        url = match.group(2).strip()
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.replace("www.", "")
        return f"{num}. [{domain}]({url})"

    md = re.sub(r'^(\d+)\.\s+(https?://[^\s]+)', linkify_url, md, flags=re.MULTILINE)

    # Convert bare (url) → [url](url)
    md = re.sub(r'\(https?://([^\s)]+)\)', r'[\1](\1)', md)

    return md


def md_to_html(md: str) -> str:
    body = md_lib.markdown(md, extensions=["extra"])

    body = body.replace('<a href="', '<a target="_blank" rel="noopener" href="')

    today = datetime.now()
    months = ["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"]
    date_ru = f"{today.day} {months[today.month-1]} {today.year}"
    gen_ts = today.strftime("%d.%m.%Y %H:%M UTC")
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Context Map — {today.strftime('%d.%m.%Y')}</title>
<style>
:root {{
  --bg: #faf9f7; --text: #1a1a1a; --text2: #6b7280;
  --border: #e5e7eb; --accent: #2563eb; --accent2: #1d4ed8;
  --w: 720px;
}}
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans",sans-serif;
  background:var(--bg);color:var(--text);line-height:1.75;font-size:17px;padding:2rem 1rem;
}}
.container{{max-width:var(--w);margin:0 auto}}
header{{margin-bottom:2.5rem;padding-bottom:1.5rem;border-bottom:1px solid var(--border)}}
header h1{{font-size:1.75rem;font-weight:700;letter-spacing:-0.02em}}
header .meta{{margin-top:0.5rem;font-size:0.875rem;color:var(--text2)}}
header .desc{{margin-top:1rem;font-size:0.9rem;color:var(--text2);line-height:1.5}}
h2{{font-size:1.35rem;margin-top:2.5rem;margin-bottom:0.75rem;font-weight:600}}
h3{{font-size:1.1rem;margin-top:1.5rem;margin-bottom:0.5rem;font-weight:600;color:var(--accent)}}
p{{margin-bottom:1rem}}
a{{color:var(--accent);text-decoration:underline;text-underline-offset:2px}}
a:hover{{color:var(--accent2)}}
ul,ol{{margin-bottom:1rem;padding-left:1.5rem}}
li{{margin-bottom:0.25rem}}
hr{{border:none;border-top:1px solid var(--border);margin:2rem 0}}
blockquote{{border-left:3px solid var(--accent);padding-left:1rem;margin:1rem 0;color:var(--text2)}}
code{{background:var(--border);padding:0.15rem 0.4rem;border-radius:4px;font-size:0.875em}}
.disclaimer{{margin-top:2.5rem;padding:1rem 1.25rem;background:#fef3cd;border-left:4px solid #f59e0b;border-radius:4px;font-size:0.85rem;color:#92400e;line-height:1.5}}
footer{{margin-top:1.5rem;padding-top:1.5rem;border-top:1px solid var(--border);font-size:0.8rem;color:var(--text2)}}
</style>
</head>
<body>
<div class="container">
<header>
  <h1>Context Map</h1>
  <div class="meta">{date_ru} · дайджест для решений о переезде в Минск</div>
  <p class="desc">Дайджест собирает геополитический контекст, важный для переезда: 7 разделов от обзорной карты до сценариев развития. Основа — новости за 3 дня, проанализированные DeepSeek V3. Не замена консультации.</p>
</header>
<main>
{body}
</main>
<div class="disclaimer">
  <p>Сгенерировано AI. Ключевые цифры и факты рекомендуем перепроверять по первоисточникам. Не является инвестиционной или юридической консультацией.</p>
</div>
<footer>
  <p>Context Map — автоматический дайджест для принятия решений.</p>
  <p style="margin-top:0.25rem;font-size:0.75rem;color:var(--text2)">Сгенерирован {gen_ts}</p>
</footer>
</div>
</body>
</html>"""
    return html


def save(html: str):
    date_str = datetime.now().strftime("%Y-%m-%d")

    idx = BASE_DIR / "index.html"
    idx.write_text(html, encoding="utf-8")
    print(f"index.html ({len(html)} bytes)")

    ad = BASE_DIR / "artifacts"
    ad.mkdir(exist_ok=True)
    ap = ad / f"{date_str}.html"
    ap.write_text(html, encoding="utf-8")
    print(f"artifacts/{date_str}.html")


def main():
    print(f"Context Map — {datetime.now().isoformat()}")

    results = search_news()
    if not results:
        print("No news, saving empty digest")
        html = "<html><body><h1>No data this cycle</h1></body></html>"
        save(html)
        return

    context = build_context(results)
    print(f"Context: {len(context)} chars / {len(results)} sources")

    md = call_llm(context)
    print(f"Digest raw: {len(md)} chars")

    md = post_process_md(md)

    html = md_to_html(md)
    save(html)
    print("Done.")


if __name__ == "__main__":
    main()
