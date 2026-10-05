# Apartment Hunter

**Авто-подбор квартир в Минске для покупки.**

Работает вместо старого Context Map (геополитический дайджест).

## Что делает

- Ищет 3-4 комнатные квартиры на Kufar.by и Realt.by через DDG
- LLM (DeepSeek V3) анализирует сниппеты, фильтрует по критериям, ранжирует
- Результат — HTML-таблица на GitHub Pages
- Обновляется 2 раза в день: 9:00 и 19:00 по Минску

## Критерии поиска

- 3-4 комнаты, до 520 000 BYN
- Не 1-й этаж, не 4-5 этаж в пятиэтажках
- Балкон/лоджия обязателен
- Зона: м. Восток — м. Октябрьская

## Как работает

DDG-поиск (9 запросов) → сбор URL+сниппетов → DeepSeek V3 (bothub.ru API) → HTML-таблица → GitHub Pages.

Стек: Python, DDGS, DeepSeek V3, GitHub Actions.

## Live

https://look85-ops.github.io/context-map/

## Fork & Adapt

Хочешь такой же подбор под свой город/бюджет?

1. В `src/apt_hunter.py`: поменяй `SEARCH_QUERIES`, `CRITERIA` и `SYSTEM_PROMPT`
2. В `.github/workflows/hunt.yml`: поменяй `cron` под свою частоту
3. Включи GitHub Pages в настройках репозитория (ветка `main`, папка `/`)