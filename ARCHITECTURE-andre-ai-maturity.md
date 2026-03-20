# Архитектура: andre-ai-maturity

Telegram-бот диагностики AI-зрелости компании. 35 вопросов по 7 категориям, детерминистический скоринг + LLM-анализ, HTML-отчёт.

---

## 1. Общая архитектура системы

```mermaid
graph TB
    subgraph "Telegram"
        TG_USER[👤 Пользователь в Telegram]
    end

    subgraph "Bot Application"
        MAIN[main.py<br/>Entry Point]
        DISPATCHER[aiogram Dispatcher<br/>Роутинг callback/команд]
        HANDLER[bot/handlers/assessment.py<br/>Обработчик /start, ответов,<br/>результатов]
        KEYBOARDS[bot/keyboards/inline.py<br/>Inline-клавиатуры]
        MESSAGES[bot/texts/messages.py<br/>Шаблоны сообщений]
    end

    subgraph "Services"
        SCORING[services/scoring.py<br/>Детерминистический скоринг]
        LLM_SERVICE[services/llm.py<br/>LLM-клиент OpenAI]
        LLM_PROMPTS[services/llm_prompts.py<br/>Системный и user промпты]
        REPORT[services/report.py<br/>HTML-генератор отчёта]
        WEB[services/web.py<br/>aiohttp веб-сервер]
    end

    subgraph "Data"
        QUESTION_BANK[data/question_bank.py<br/>35 вопросов × 7 категорий]
        CONFIG[config.py<br/>Переменные окружения]
    end

    subgraph "Database"
        DB[(SQLite<br/>ai_maturity.db)]
        MODELS[db/models.py<br/>Схема БД]
        STORAGE[db/storage.py<br/>CRUD-операции]
    end

    subgraph "External"
        OPENAI_API[OpenAI-совместимый API<br/>gpt-4o-mini]
        BROWSER[🌐 Браузер<br/>HTML-отчёт]
    end

    TG_USER <-->|Telegram Bot API| DISPATCHER
    MAIN --> DISPATCHER
    MAIN --> DB
    MAIN --> WEB
    DISPATCHER --> HANDLER
    HANDLER --> KEYBOARDS
    HANDLER --> MESSAGES
    HANDLER --> SCORING
    HANDLER --> LLM_SERVICE
    HANDLER --> REPORT
    HANDLER --> WEB
    HANDLER --> STORAGE
    SCORING --> QUESTION_BANK
    LLM_SERVICE --> LLM_PROMPTS
    LLM_SERVICE --> OPENAI_API
    LLM_SERVICE --> CONFIG
    LLM_PROMPTS --> QUESTION_BANK
    STORAGE --> DB
    MODELS --> DB
    WEB -->|GET /report/ID| BROWSER
    MESSAGES --> QUESTION_BANK
```

---

## 2. Последовательность работы (User Flow)

```mermaid
sequenceDiagram
    actor User as 👤 Пользователь
    participant TG as Telegram Bot
    participant Handler as assessment.py
    participant Storage as db/storage.py
    participant DB as SQLite
    participant Scoring as scoring.py
    participant LLM as llm.py + llm_prompts.py
    participant OpenAI as OpenAI API
    participant Report as report.py
    participant Web as web.py
    participant Browser as 🌐 Браузер

    User->>TG: /start
    TG->>Handler: cmd_start()
    Handler->>Storage: get_or_create_user()
    Storage->>DB: SELECT/INSERT users
    Handler->>Storage: get_active_assessment()
    Storage->>DB: SELECT assessments
    Handler->>TG: welcome_text + start_keyboard

    User->>TG: 🚀 Начать диагностику
    TG->>Handler: on_start_assessment()
    Handler->>Storage: create_assessment()
    Storage->>DB: INSERT assessment (status=in_progress)
    Handler->>TG: Вопрос 1/35

    loop 35 вопросов
        User->>TG: Нажимает кнопку ответа (1-5 или "Не знаю")
        TG->>Handler: on_answer(q_index, value)
        Handler->>Storage: save_answer()
        Storage->>DB: INSERT/UPDATE answers
        Handler->>Storage: update_assessment_progress()
        Storage->>DB: UPDATE assessment.current_question_index
        Handler->>TG: Следующий вопрос
    end

    Note over Handler: Последний вопрос отвечен

    Handler->>Scoring: calculate_results(answers)
    Scoring-->>Handler: {total_percent, maturity_level, categories, strengths, weaknesses}
    Handler->>Storage: complete_assessment(result)
    Storage->>DB: UPDATE assessment (status=completed, result_json)
    Handler->>TG: 📊 Результат (детерминистический)

    Handler->>TG: ⏳ Генерирую расширенный анализ...

    Handler->>LLM: generate_analysis(result, answers)
    LLM->>LLM: build_user_prompt(result, answers)
    LLM->>OpenAI: chat.completions.create(system + user prompt)
    OpenAI-->>LLM: LLM-ответ (SWOT, рекомендации)
    LLM-->>Handler: analysis text

    Handler->>TG: Удалить сообщение "⏳"

    Handler->>Report: generate_html_report(result, analysis)
    Report-->>Handler: HTML-страница
    Handler->>Web: save_report(html) → report_id
    Web-->>Handler: report_url

    Handler->>Storage: save_llm_analysis(analysis)
    Storage->>DB: UPDATE assessment.llm_analysis
    Handler->>TG: LLM-анализ + 📎 ссылка на отчёт

    User->>Browser: Открывает ссылку /report/{id}
    Browser->>Web: GET /report/{report_id}
    Web-->>Browser: HTML-отчёт
```

---

## 3. Структура базы данных (SQLite)

```mermaid
erDiagram
    users {
        INTEGER id PK "AUTOINCREMENT"
        INTEGER telegram_user_id UK "NOT NULL"
        TEXT username
        TEXT first_name
        TEXT last_name
        TIMESTAMP created_at "DEFAULT CURRENT_TIMESTAMP"
    }

    assessments {
        INTEGER id PK "AUTOINCREMENT"
        INTEGER user_id FK "NOT NULL → users.id"
        TEXT status "in_progress | completed | abandoned"
        TIMESTAMP started_at "DEFAULT CURRENT_TIMESTAMP"
        TIMESTAMP completed_at
        INTEGER current_question_index "DEFAULT 0"
        REAL total_score_percent
        TEXT maturity_level
        TEXT reliability_level
        TEXT result_json "Полный JSON результата"
        TEXT llm_analysis "Текст LLM-анализа"
    }

    answers {
        INTEGER id PK "AUTOINCREMENT"
        INTEGER assessment_id FK "NOT NULL → assessments.id"
        TEXT question_code "NOT NULL (str_1, ppl_2, ...)"
        TEXT category_code "NOT NULL (strategy, people, ...)"
        INTEGER option_value "1-5 или NULL"
        INTEGER score "1-5 или NULL"
        INTEGER is_unknown "0 или 1"
        TIMESTAMP answered_at "DEFAULT CURRENT_TIMESTAMP"
    }

    users ||--o{ assessments : "has many"
    assessments ||--o{ answers : "has many"
```

---

## 4. Алгоритм скоринга

```mermaid
flowchart TD
    A[Получить все ответы assessment] --> B[Сгруппировать по категориям]
    B --> C[Посчитать unknown_count]

    C --> D{Для каждой из 7 категорий}
    D --> E[scores = ответы 1-5<br/>без 'Не знаю']
    E --> F["avg = sum(scores) / count"]
    F --> G["percent = ((avg - 1) / 4) × 100"]
    G --> H{"valid_count < 3?"}
    H -->|Да| I["Пометить tentative ≈"]
    H -->|Нет| J[Обычная оценка]

    I --> K[Взвешенное среднее]
    J --> K

    K --> L["weighted_avg = Σ(avg × weight) / Σ(weights)"]
    L --> M["total_percent = ((weighted_avg - 1) / 4) × 100"]

    M --> N{total_percent}
    N -->|0-20%| N1[Начальный]
    N -->|21-40%| N2[AI-Enabled]
    N -->|41-60%| N3[AI-Driven]
    N -->|61-80%| N4[AI-First]
    N -->|81-100%| N5[AI-Native]

    C --> O{unknown_count}
    O -->|0-3| P[Надёжность: Высокая]
    O -->|4-8| Q[Надёжность: Средняя]
    O -->|9+| R[Надёжность: Низкая]

    M --> S[Top 3 сильные стороны<br/>Top 3 зоны роста]
```

### Веса категорий

```mermaid
pie title Веса категорий в общем индексе
    "🎯 Стратегия (0.15)" : 15
    "👥 Люди (0.15)" : 15
    "🏗 Инфраструктура (0.15)" : 15
    "🗂 Данные (0.15)" : 15
    "🧠 Модели (0.15)" : 15
    "⚙️ Внедрение (0.20)" : 20
    "🔬 R&D (0.05)" : 5
```

---

## 5. AI / LLM — промпты и последовательность

### 5.1 Архитектура вызова LLM

```mermaid
flowchart LR
    subgraph Input
        RESULT[Результат скоринга<br/>total_percent, categories,<br/>strengths, weaknesses]
        ANSWERS[Ответы пользователя<br/>35 вопросов + выбранные варианты]
        QBANK[Банк вопросов<br/>тексты и опции]
    end

    subgraph "llm_prompts.py"
        SYS[SYSTEM_PROMPT<br/>Роль эксперта +<br/>правила + уровни]
        BUILD["build_user_prompt()"]
        USER[USER_PROMPT_TEMPLATE<br/>Данные + формат ответа]
    end

    subgraph "llm.py"
        CLIENT[AsyncOpenAI Client]
        CALL["chat.completions.create()"]
        FALLBACK["get_fallback_analysis()<br/>Если LLM недоступен"]
    end

    subgraph "OpenAI API"
        API[gpt-4o-mini<br/>temperature=0.7<br/>max_completion_tokens=1500]
    end

    RESULT --> BUILD
    ANSWERS --> BUILD
    QBANK --> BUILD
    BUILD --> USER
    SYS --> CALL
    USER --> CALL
    CALL --> CLIENT
    CLIENT --> API
    API -->|Ответ| OUTPUT[LLM-анализ:<br/>📊 Интерпретация<br/>📋 SWOT<br/>💡 Рекомендации]
    CLIENT -->|Ошибка| FALLBACK
    FALLBACK --> FALLBACK_OUT[Заглушка по уровню<br/>зрелости]
```

### 5.2 SYSTEM_PROMPT (полный текст)

```
Ты — эксперт по цифровой трансформации и внедрению ИИ в компаниях.
Тебе дают результаты диагностики AI-зрелости компании.
Твоя задача — дать краткий, конкретный и полезный анализ.

Правила:
- Пиши на русском языке.
- Будь максимально кратким — весь ответ СТРОГО до 2000 символов.
- Не повторяй числовые результаты — они уже показаны пользователю.
- Не придумывай факты о компании.
- Не используй маркетинговый язык и воду.
- Давай практичные, применимые советы.
- Формат ответа — текст с эмодзи-заголовками, без markdown-разметки.
- ЗАПРЕЩЕНО добавлять разделы, которых нет в шаблоне.
- Ответ содержит РОВНО 3 раздела: Интерпретация, SWOT, Рекомендации.

Уровни зрелости (ориентир):
1. Начальный (0-20%): ИИ хаотично. Назначить ответственных, зафиксировать метрики, quick wins.
2. AI-Enabled (21-40%): ИИ локально. Стратегия, центр компетенций, ROI.
3. AI-Driven (41-60%): ИИ в процессах. Масштабировать, AgentOps/MLOps/Governance.
4. AI-First (61-80%): ИИ в операционной модели. Автономность, ИИ-платформа, KPI, R&D.
5. AI-Native (81-100%): ИИ — основа бизнеса. Собственные модели, новые рынки, выручка от ИИ.
```

### 5.3 USER_PROMPT_TEMPLATE (шаблон с подстановкой)

```
Результаты диагностики AI-зрелости компании:

Общий индекс: {total_percent}%
Уровень зрелости: {maturity_level}
Надежность результата: {reliability}

Результаты по категориям:
  🎯 Стратегия и управление: 35%
  👥 Люди и культура: 20%
  ...

Сильные стороны: 🎯 Стратегия (35%), ...
Зоны роста: 🔬 R&D (0%), ...

Ответы пользователя:
  Есть ли у компании ИИ-стратегия? → В процессе. ИИ-стратегия в разработке...
  Насколько вовлечено руководство? → Не знаю
  ...

Дай анализ СТРОГО в этом формате, РОВНО 3 раздела, до 2000 символов:

📊 Интерпретация
Сплошной текст, 2-3 предложения.

📋 SWOT-анализ
S: текст
W: текст
O: текст
T: текст

💡 Рекомендации
🚀 Быстрые шаги (сейчас): ...
📅 Среднесрочные (1-3 месяца): ...
🎯 Долгосрочные (3-6 месяцев): ...
```

### 5.4 Fallback (при недоступности LLM)

```mermaid
flowchart TD
    LLM_CALL[Вызов OpenAI API] -->|Ошибка или нет API-ключа| FALLBACK

    FALLBACK{"maturity_level?"}
    FALLBACK -->|Начальный| F1["ИИ используется хаотично...<br/>💡 Определить 3-5 процессов,<br/>назначить ответственных,<br/>зафиксировать метрики, quick wins"]
    FALLBACK -->|AI-Enabled| F2["Компания использует ИИ-инструменты...<br/>💡 От инструментов к процессам,<br/>стратегия, центр компетенций, ROI"]
    FALLBACK -->|AI-Driven| F3["ИИ встроен в ключевые процессы...<br/>💡 Перестраивать процессы,<br/>AgentOps, MLOps, Data Governance"]
    FALLBACK -->|AI-First| F4["ИИ — часть операционной модели...<br/>💡 Автономность, ИИ-платформа,<br/>KPI, R&D-контур"]
    FALLBACK -->|AI-Native| F5["ИИ — основа бизнес-модели...<br/>💡 Собственные модели, R&D,<br/>новые рынки, выручка от ИИ"]

    F1 --> WARN["⚠️ Расширенный анализ<br/>(SWOT, рекомендации) недоступен"]
    F2 --> WARN
    F3 --> WARN
    F4 --> WARN
    F5 --> WARN
```

---

## 6. Компоненты и файлы

```mermaid
graph LR
    subgraph "Entry Point"
        main.py
    end

    subgraph "config"
        config.py
        .env
    end

    subgraph "bot/"
        bot/handlers/assessment.py
        bot/keyboards/inline.py
        bot/texts/messages.py
    end

    subgraph "services/"
        services/scoring.py
        services/llm.py
        services/llm_prompts.py
        services/report.py
        services/web.py
    end

    subgraph "data/"
        data/question_bank.py
    end

    subgraph "db/"
        db/models.py
        db/storage.py
    end

    subgraph "Файловая система"
        reports/["reports/*.html"]
    end
```

---

## 7. Сервисы и их ответственности

| Сервис | Файл | Ответственность |
|--------|-------|-----------------|
| **Telegram Bot** | `bot/handlers/assessment.py` | Обработка команд `/start`, callback-кнопок, навигация по вопросам, показ результатов |
| **Keyboards** | `bot/keyboards/inline.py` | Генерация inline-клавиатур: старт, вопросы (5 ответов + "Не знаю" + Назад + Прервать), подтверждения |
| **Messages** | `bot/texts/messages.py` | Шаблоны текстов: welcome, question, result, abort/restart |
| **Scoring** | `services/scoring.py` | Детерминистический расчёт: среднее по категориям, взвешенный индекс, уровень зрелости, надёжность, сильные/слабые стороны |
| **LLM Service** | `services/llm.py` | Вызов OpenAI API, fallback-анализ при недоступности |
| **LLM Prompts** | `services/llm_prompts.py` | System prompt (роль + правила), user prompt template, сборка промпта из результатов |
| **Report** | `services/report.py` | Генерация HTML-отчёта (Tailwind CSS, glass-morphism, dark/light тема, анимированные блобы) |
| **Web Server** | `services/web.py` | aiohttp-сервер для раздачи HTML-отчётов по `/report/{id}`, сохранение на диск |
| **Storage** | `db/storage.py` | CRUD: users, assessments, answers |
| **Models** | `db/models.py` | DDL-схема SQLite (3 таблицы) |
| **Question Bank** | `data/question_bank.py` | 35 вопросов, 7 категорий с весами, тексты опций и кнопок |
| **Config** | `config.py` | BOT_TOKEN, LLM_API_KEY, LLM_MODEL, LLM_BASE_URL, DATABASE_PATH, REPORT_BASE_URL, REPORT_PORT |

---

## 8. Технологический стек

```mermaid
graph LR
    subgraph "Runtime"
        Python["Python 3.11+"]
    end

    subgraph "Telegram"
        aiogram["aiogram 3.15<br/>Bot API framework"]
    end

    subgraph "LLM"
        openai["OpenAI SDK 1.58<br/>AsyncOpenAI"]
    end

    subgraph "Database"
        aiosqlite["aiosqlite 0.20<br/>Async SQLite"]
    end

    subgraph "Web"
        aiohttp["aiohttp 3.9+<br/>HTTP-сервер для отчётов"]
    end

    subgraph "Frontend (в HTML-отчёте)"
        Tailwind["Tailwind CSS (CDN)"]
        JetBrains["JetBrains Mono"]
        FontAwesome["Font Awesome 6"]
    end

    Python --> aiogram
    Python --> openai
    Python --> aiosqlite
    Python --> aiohttp
```

---

## 9. Параметры LLM-вызова

| Параметр | Значение |
|----------|----------|
| **Модель** | `gpt-4o-mini` (настраивается через `LLM_MODEL`) |
| **Base URL** | `https://api.openai.com/v1` (настраивается через `LLM_BASE_URL`) |
| **Temperature** | `0.7` |
| **Max completion tokens** | `1500` |
| **Формат ответа** | Текст с эмодзи-заголовками, без markdown |
| **Лимит** | Строго до 2000 символов |
| **Язык** | Русский |
| **Структура ответа** | 3 раздела: Интерпретация → SWOT → Рекомендации (быстрые/среднесрочные/долгосрочные) |
