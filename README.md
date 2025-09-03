# Руководство по Prompt Engineering (конспект + практикум)

**Язык:** русский  
**Источник:** перевод и конспект цикла «Prompt Engineering» от Google (Lee Boonstra) — части 1–3 на Хабре.  
**Для кого:** инженеры/аналитики, которые хотят быстро поставить на поток разработку и проверку промптов.

> Репозиторий содержит полный **конспект** (`notebooks.mk`), готовые **шаблоны промптов** и **практические задания**. Можно использовать с любым провайдером LLM (OpenAI‑совместимые API, GigaChat и др.) — см. `scripts/run.py` и `.env.example`.

## Содержание

- `notebooks.mk` — конспект по трём частям гайда Google: базовые техники, продвинутые методы и лучшие практики.
- `prompts/` — коллекция шаблонов:
  - `patterns/` — Zero/One/Few‑shot; System/Role/Context; делимитеры; JSON‑контракты; пошаговые рассуждения; Step‑back; ReAct.
- `exercises/` — набор задач с чек‑листами и критериями приёмки.
- `scripts/run.py` — минимальный CLI для прогона шаблонов (OpenAI‑совместимые API и GigaChat через токен).
- `.env.example` — переменные окружения.
- `requirements.txt` — зависимости (минимум).
- `LICENSE` — MIT.

## Быстрый старт

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# укажите провайдера и ключи (OPENAI_API_KEY или GIGACHAT_AUTH_KEY/CLIENT_ID/SCOPE)

# запустить тестовый шаблон
python scripts/run.py chat --prompt-file prompts/patterns/01_zero_shot.md --var topic="история Kubernetes"
```

### Настройка провайдера
В `.env` задайте:
- `PROVIDER=openai` **или** `PROVIDER=gigachat`
- Для OpenAI‑совместимых: `OPENAI_API_BASE` (опц.), `OPENAI_API_KEY`
- Для GigaChat: `GIGACHAT_AUTH_KEY`, `GIGACHAT_CLIENT_ID`, `GIGACHAT_SCOPE=GIGACHAT_API_PERS`

> **Примечание:** код не привязан к конкретной модели. Выберите модель командой `--model` (по умолчанию: провайдер‑дефолт).

## Откуда материал

- Часть 1 — основы и базовые техники (температура, Top‑K/Top‑P, Zero/One/Few‑shot, System/Role/Context, контекст, делимитеры, формат вывода).  
- Часть 2 — продвинутые техники (Step‑back, Chain of Thought, Self‑consistency, Tree of Thoughts, ReAct, APE, промптинг для кода).  
- Часть 3 — лучшие практики (давайте примеры, проектируйте просто, будьте конкретны, используйте инструкции, контролируйте длину, переменные, CoT‑best‑practices, документируйте эксперименты).

Ссылки на переводы и оригинал смотрите в верхней части `notebooks.mk`.


## Банковский домен (готовые артефакты)
- **Чек-лист RAG/FAQ:** `banking/checklists/rag_relevancy_checklist.md`
- **Негативные кейсы:** `banking/negative_tests/faq_negatives.md`
- **JSON-схемы:** `banking/schemas/*.json` (перевыпуск карты, жалоба, реквизиты)
- **Промпты:** `prompts/banking/*` (ответ с цитатами, триаж жалоб, извлечение реквизитов)
- **CLI‑валидация JSON:** `python scripts/run.py chat --prompt-file ... --schema banking/schemas/complaint_schema.json`

Эти материалы соответствуют описанию в портфолио: техники (System/Role/Context, Few‑shot, CoT, ReAct), настройки вывода, чек‑листы и шаблоны под банковский домен.

## Развёртывание на Streamlit Cloud

1. Загрузите этот репозиторий на GitHub.
2. Зайдите в [streamlit.io](https://streamlit.io/cloud) → **New app** → подключите ваш репозиторий.  
   В качестве entry‑file укажите `streamlit_app.py`.
3. В разделе **Settings → Secrets** вставьте секреты, например:
   ```toml
   OPENAI_API_KEY = "sk-..."
   OPENAI_API_BASE = "https://api.openai.com/v1"
   OPENAI_MODEL = "gpt-4o-mini"
   # или GigaChat:
   GIGACHAT_AUTH_KEY = "base64(client_id:client_secret)"
   GIGACHAT_SCOPE = "GIGACHAT_API_PERS"
   GIGACHAT_MODEL = "GigaChat-Pro"
   ```
4. Нажмите **Deploy**. Приложение позволит:
   - выбрать шаблон промпта из `prompts/**`;
   - подставить переменные;
   - выполнить запрос через выбранного провайдера;
   - при желании провалидировать ответ по JSON‑схеме из `banking/schemas/*.json` или загруженной.
