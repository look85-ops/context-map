# Context Map

**Геополитический дайджест для решений о переезде в Минск.**  
**Geopolitical digest for relocation decisions to Minsk.**

---

## RU

**Context Map** — автоматический дайджест, который собирает геополитический контекст, важный для переезда из РФ в Беларусь. Генерируется раз в 3 дня на основе свежих новостей, отфильтрованных от пропагандистских источников.

### Что внутри

1. **Обзорная карта** — ключевой тренд, главный риск, главная возможность
2. **Поле боя** — ситуация в РФ, РБ, Украине и мире (только то, что влияет на жизнь)
3. **Слабые сигналы** — edge signals, которые не в мейнстриме, но могут выстрелить
4. **Устойчивые паттерны** — тренды, подтверждённые 3+ периодов
5. **Влияние на решения** — работа, недвижимость, деньги, отрасли (с цифрами и конкретикой)
6. **Сценарии** — базовый / эскалация / деэскалация на 1-3 мес с триггерами
7. **Дополнительно** — слепые пятна и неочевидные факторы

### Как работает

Новости собираются через DuckDuckGo → фильтрация от пропаганды → анализ DeepSeek V3 → генерация HTML. Всё в GitHub Actions.

### Стек

- Python (curator.py)
- DuckDuckGo Search (ddgs)
- DeepSeek V3 (bothub.ru API)
- GitHub Actions (cron каждые 3 дня)
- GitHub Pages (хостинг)

---

## EN

**Context Map** is an auto-generated digest that monitors geopolitical developments relevant to relocating from Russia to Belarus. Updated every 3 days.

### Contents

1. Overview — key trend, main risk, main opportunity
2. Situation — Russia, Belarus, Ukraine, World
3. Weak signals — edge cases that may shift the landscape
4. Stable patterns — trends confirmed over 3+ cycles
5. Impact on decisions — jobs, real estate, money, industries
6. Scenarios — baseline / escalation / de-escalation with triggers
7. Additional — blind spots worth watching

### How it works

News collected via DuckDuckGo → propaganda filtering → DeepSeek V3 analysis → HTML output. Runs on GitHub Actions.

### Stack

Python, DuckDuckGo Search, DeepSeek V3 (bothub.ru), GitHub Actions, GitHub Pages.

---

**Live:** https://look85-ops.github.io/context-map/
