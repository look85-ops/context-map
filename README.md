# Context Map

**Геополитический дайджест для переезжающих и переехавших в Беларусь из РФ.**  
**Geopolitical digest for those relocating to Minsk or already there.**

---

## RU

**Context Map** — автоматический дайджест, который собирает геополитический контекст, важный для переезда и жизни в Минске. Генерируется дважды в неделю (пн, ср) на основе свежих новостей, отфильтрованных от пропагандистских источников.

### Что внутри

1. **Обзорная карта** — ключевой тренд, главный риск, главная возможность
2. **Поле боя** — ситуация в РФ, РБ, Украине и мире (только то, что влияет на жизнь)
3. **Слабые сигналы** — edge signals, которые не в мейнстриме, но могут выстрелить
4. **Устойчивые паттерны** — тренды, подтверждённые 3+ периодов
5. **Влияние на решения** — работа, недвижимость, деньги, отрасли (с цифрами и конкретикой)
6. **Сценарии** — базовый / эскалация / деэскалация на 1-3 мес с триггерами
7. **Дополнительно** — слепые пятна и неочевидные факторы

### Как работает

Новости собираются через DuckDuckGo → фильтрация от пропаганды → анализ ИИ → генерация HTML. Всё в GitHub Actions.

### Стек

- Python (curator.py)
- DuckDuckGo Search (ddgs)
- DeepSeek V3 (bothub.ru API)
- GitHub Actions (cron пн, ср)
- GitHub Pages (хостинг)

---

## EN

**Context Map** is an auto-generated digest that monitors geopolitical developments relevant to relocating to or living in Minsk. Updated twice a week (Mon, Wed).

### Contents

1. Overview — key trend, main risk, main opportunity
2. Situation — Russia, Belarus, Ukraine, World
3. Weak signals — edge cases that may shift the landscape
4. Stable patterns — trends confirmed over 3+ cycles
5. Impact on decisions — jobs, real estate, money, industries
6. Scenarios — baseline / escalation / de-escalation with triggers
7. Additional — blind spots worth watching

### How it works

News collected via DuckDuckGo → propaganda filtering → AI analysis → HTML output. Runs on GitHub Actions.

### Stack

Python, DuckDuckGo Search, DeepSeek V3 (bothub.ru), GitHub Actions (Mon, Wed), GitHub Pages.

---

**Live:** https://look85-ops.github.io/context-map/

### Fork & Adapt для другого региона

Хочешь сделать такой дайджест под свой город/страну? Форкни репозиторий и поменяй:

1. В `src/curator.py`: `SEARCH_QUERIES` (ключевые слова для поиска) и `SYSTEM_PROMPT` (описание твоей аудитории)
2. В `.github/workflows/digest.yml`: `cron` (частоту генерации)
3. Включи GitHub Pages в настройках репозитория (ветка `main`, папка `/`)

Изменения в репозиторий вносятся **только через fork** — пул-реквесты не принимаю, это личный инструмент.

**Repo:** https://github.com/look85-ops/context-map
