#!/usr/bin/env python3
"""
Context Map — geopolitical digest for relocation decisions.
Searches news, summarizes via DeepSeek V3, generates HTML.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from ddgs import DDGS
import markdown as md_lib

API_KEY = os.environ.get("GH_TOKEN", "")
if not API_KEY:
    print("FATAL: GH_TOKEN not set")
    sys.exit(1)

BASE_URL = "https://models.inference.ai.azure.com"
MODEL = "DeepSeek-V3-0324"

BASE_DIR = Path(__file__).resolve().parent.parent

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

SYSTEM_PROMPT = """Ты — аналитический ассистент Context Map. Составляешь дайджест для девушки (Наташа), планирующей переезд в Минск из РФ.

Ты получаешь сырые фрагменты новостей за 3 дня. Генерируешь структурированный дайджест в Markdown.

СТРУКТУРА:

# Context Map — Дайджест {date}

## 1. Обзорная карта
Ключевой тренд периода. Главный риск. Главная возможность. (1-2 абзаца)

## 2. Поле боя
### РФ
### РБ
### Украина
### Мир
В каждом — только то, что влияет на жизнь/экономику.

## 3. Слабые сигналы
3-5 edge signals — не в мейнстриме, но может выстрелить.

## 4. Устойчивые паттерны
Что подтверждается 3+ периодов подряд.

## 5. Влияние на решения
### Работа
### Недвижимость
### Деньги (сохранение, инвестиции, валюта)
### Отрасли (рост/угасание)

## 6. Сценарии на 1-3 мес
3 варианта: базовый / эскалация / деэскалация. К каждому триггеры.

## 7. Дополнительно
Слабый сигнал или очевидное, но незамеченное.

---

ПРАВИЛА (НАРУШЕНИЕ НЕДОПУСТИМО):
- Каждый факт — ссылка в формате [текст](url). Запрещены голые [1][2][3] без URL
- Нижний блок "Источники" — список кликабельных ссылок [N](url)
- Лаконично: 1-3 абзаца на раздел
- Без воды: без "важно отметить", "следует подчеркнуть"
- Нет данных — прочерк (—)
- Тон: спокойный, аналитический. Ноль паники, ноль хайпа."""


def search_news() -> list[dict]:
    seen = set()
    results = []
    with DDGS() as ddgs:
        for query in SEARCH_QUERIES:
            try:
                for r in ddgs.text(query, max_results=4):
                    url = r.get("href", "")
                    if url and url not in seen:
                        seen.add(url)
                        results.append({
                            "title": r.get("title", ""),
                            "snippet": r.get("body", ""),
                            "url": url,
                        })
            except Exception as e:
                print(f"Search fail '{query}': {e}")
    print(f"Collected {len(results)} unique items")
    return results


def build_context(results: list[dict]) -> str:
    lines = ["## Новости за 3 дня\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"### {i}. {r['title']}")
        lines.append(r["snippet"])
        lines.append(f"Source: {r['url']}\n")
    return "\n".join(lines)


def call_llm(context: str) -> str:
    today = datetime.now().strftime("%d.%m.%Y")
    system = SYSTEM_PROMPT.format(date=today)

    resp = requests.post(
        f"{BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": context},
            ],
            "temperature": 0.7,
            "max_tokens": 8192,
        },
        timeout=120,
    )

    if resp.status_code != 200:
        raise Exception(f"API {resp.status_code}: {resp.text}")

    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    print(f"LLM: {usage.get('prompt_tokens','?')} in / {usage.get('completion_tokens','?')} out")
    return content


def md_to_html(md: str) -> str:
    body = md_lib.markdown(md, extensions=["extra"])

    body = body.replace('<a href="', '<a target="_blank" rel="noopener" href="')

    today = datetime.now()
    date_ru = today.strftime("%d %B %Y")
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
footer{{margin-top:3rem;padding-top:1.5rem;border-top:1px solid var(--border);font-size:0.8rem;color:var(--text2)}}
</style>
</head>
<body>
<div class="container">
<header>
  <h1>Context Map</h1>
  <div class="meta">{date_ru} · дайджест каждые 3 дня</div>
</header>
<main>
{body}
</main>
<footer>
  <p>Context Map — автоматический дайджест для принятия решений.</p>
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
    print(f"Digest: {len(md)} chars")

    html = md_to_html(md)
    save(html)
    print("Done.")


if __name__ == "__main__":
    main()
