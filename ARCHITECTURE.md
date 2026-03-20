# AIT-OS — Архитектура системы

Telegram-бот для автоматизированного сбора, анализа и публикации описаний бизнес-процессов AS-IS с помощью LLM (GPT-5.4).

---

## 1. Общая архитектура системы

```mermaid
graph TB
    subgraph "Пользователь"
        TG_USER[Telegram User]
    end

    subgraph "Telegram Bot (python-telegram-bot 21+)"
        MAIN[main.py — Entry Point]
        HANDLERS[Handlers Layer]
        SERVICES[Services Layer]
        PROMPTS[Prompts — .txt шаблоны]
    end

    subgraph "Внешние API"
        OPENAI_CHAT[OpenAI Chat Completions API — GPT-5.4]
        OPENAI_WHISPER[OpenAI Whisper API — STT]
    end

    subgraph "Хранилище"
        SQLITE[(SQLite — bot.db)]
        PAGES_FS[File System — HTML/PDF pages]
    end

    subgraph "Web-сервер (aiohttp)"
        WEB[web.py — HTTP-сервер для опубликованных страниц]
    end

    TG_USER <-->|Telegram Bot API| MAIN
    MAIN --> HANDLERS
    HANDLERS --> SERVICES
    SERVICES --> PROMPTS
    SERVICES -->|chat completions| OPENAI_CHAT
    SERVICES -->|transcriptions| OPENAI_WHISPER
    SERVICES -->|SQLAlchemy async| SQLITE
    SERVICES -->|Jinja2 + WeasyPrint| PAGES_FS
    WEB -->|static files| PAGES_FS
    TG_USER -->|HTTP GET| WEB
```

---

## 2. Структура сервисов и их ответственность

```mermaid
graph LR
    subgraph "Handlers — обработка взаимодействий"
        H_START[start.py — /start, навигация, создание процесса]
        H_INTERVIEW[interview.py — приём текста/голоса/файлов]
        H_CLARIFICATION[clarification.py — 5-шаговый Q&A]
        H_CALLBACKS[callbacks.py — inline-кнопки]
        H_OPPORTUNITIES[opportunities.py — выбор возможностей автоматизации]
        H_PROGRESS[progress.py — прогресс-бар]
    end

    subgraph "Services — бизнес-логика и LLM"
        S_LLM[llm.py — OpenAI API обёртка]
        S_TRANSCRIPTION[transcription.py — Whisper STT]
        S_EXTRACTOR[extractor.py — LLM Call 1: извлечение AS-IS модели]
        S_GAP[gap_detector.py — LLM Call 2: обнаружение пробелов]
        S_CLARIFICATION[clarification.py — LLM Call 2a/2b: уточняющие вопросы]
        S_GENERATOR[generator.py — LLM Call 3: нарративное описание]
        S_MERMAID[mermaid.py — LLM Call 4: Mermaid-диаграмма]
        S_OPPORTUNITIES[opportunities.py — LLM Call 5: возможности автоматизации]
        S_PUBLISHER[publisher.py — сборка HTML страницы]
        S_PDF[pdf_converter.py — HTML → PDF]
    end

    H_INTERVIEW --> S_TRANSCRIPTION
    H_INTERVIEW --> S_EXTRACTOR
    H_INTERVIEW --> S_GAP
    H_CLARIFICATION --> S_CLARIFICATION
    H_CLARIFICATION --> S_GENERATOR
    H_CLARIFICATION --> S_MERMAID
    H_CLARIFICATION --> S_PUBLISHER
    H_CLARIFICATION --> S_PDF
    H_CLARIFICATION --> S_OPPORTUNITIES
    H_OPPORTUNITIES --> S_OPPORTUNITIES

    S_EXTRACTOR --> S_LLM
    S_GAP --> S_LLM
    S_CLARIFICATION --> S_LLM
    S_GENERATOR --> S_LLM
    S_MERMAID --> S_LLM
    S_OPPORTUNITIES --> S_LLM
```

---

## 3. Полный жизненный цикл процесса (State Machine)

```mermaid
stateDiagram-v2
    [*] --> CREATED: /start → Создать процесс

    CREATED --> INTERVIEW_IN_PROGRESS: Пользователь отправляет описание

    INTERVIEW_IN_PROGRESS --> INTERVIEW_IN_PROGRESS: Дополнительные сообщения (текст/голос/файл)

    INTERVIEW_IN_PROGRESS --> CLARIFICATION_IN_PROGRESS: Автоанализ → gaps detected

    CLARIFICATION_IN_PROGRESS --> CLARIFICATION_IN_PROGRESS: Q&A (до 5 вопросов)

    CLARIFICATION_IN_PROGRESS --> ASIS_READY: Все вопросы пройдены → генерация AS-IS

    ASIS_READY --> ASIS_PUBLISHED: Публикация HTML + PDF

    ASIS_PUBLISHED --> AUTOMATION_SELECTION_IN_PROGRESS: Генерация возможностей автоматизации

    AUTOMATION_SELECTION_IN_PROGRESS --> READY_FOR_TOBE: Пользователь выбрал возможности

    note right of CREATED: Имя процесса сохранено
    note right of INTERVIEW_IN_PROGRESS: Whisper → Extract → Gap Detect
    note right of CLARIFICATION_IN_PROGRESS: 5 типов вопросов по порядку
    note right of ASIS_READY: Narrative + Mermaid + HTML
    note right of AUTOMATION_SELECTION_IN_PROGRESS: Multi-select UI
```

### Состояния сессии интервью (SessionStatus)

```mermaid
stateDiagram-v2
    [*] --> STARTED: Сессия создана

    STARTED --> AWAITING_INITIAL_RESPONSE: Ожидание первого сообщения

    AWAITING_INITIAL_RESPONSE --> PROCESSING_INPUT: Получено сообщение

    PROCESSING_INPUT --> AWAITING_FOLLOWUP_ANSWER: LLM обработка завершена

    AWAITING_FOLLOWUP_ANSWER --> PROCESSING_INPUT: Новый ответ пользователя

    PROCESSING_INPUT --> PAUSED: Пауза
    PAUSED --> PROCESSING_INPUT: Возобновление

    AWAITING_FOLLOWUP_ANSWER --> COMPLETED: Все вопросы заданы
    PROCESSING_INPUT --> COMPLETED: Достаточно данных
```

---

## 4. Пайплайн LLM-вызовов и промтов

```mermaid
sequenceDiagram
    actor User as Telegram User
    participant Bot as Bot Handlers
    participant Whisper as Whisper API (STT)
    participant LLM as OpenAI GPT-5.4
    participant DB as SQLite
    participant Pub as Publisher

    Note over User,Pub: === Фаза 1: Интервью ===

    User->>Bot: Текст / Голос / Файл

    alt Голосовое сообщение
        Bot->>Whisper: audio file (language=ru)
        Whisper-->>Bot: transcript_text
    end

    Bot->>DB: Сохранить raw_input

    Note over Bot,LLM: LLM Call 1: extractor.txt
    Bot->>LLM: system: extractor.txt<br/>user: "Процесс: {name}<br/>Записи интервью: {texts}"
    LLM-->>Bot: JSON AS-IS модель (stages, roles, systems...)
    Bot->>DB: Сохранить asis_model

    Note over Bot,LLM: LLM Call 2: gap_detector.txt
    Bot->>LLM: system: gap_detector.txt<br/>user: "Процесс: {name}<br/>Модель AS-IS: {model_json}"
    LLM-->>Bot: JSON {completeness_score, gaps[]}
    Bot->>DB: Сохранить gaps + completeness_score

    Note over User,Pub: === Фаза 2: Уточнение (5-Step Q&A) ===

    Note over Bot,LLM: LLM Call 2a: clarification_questions.txt
    Bot->>LLM: system: clarification_questions.txt<br/>user: "Процесс: {name}<br/>Модель AS-IS: {model_json}"
    LLM-->>Bot: JSON {questions: [{field_type, include, question, suggestions}]}

    loop Для каждого вопроса (max 5)
        Bot->>User: Вопрос + кнопки-подсказки + "Пропустить"

        alt Пользователь отвечает
            User->>Bot: Текст / Голос ответ

            Note over Bot,LLM: LLM Call 2b: answer_extractor.txt
            Bot->>LLM: system: answer_extractor.txt<br/>user: "field_type: {type}<br/>Вопрос: {q}<br/>Ответ: {answer}<br/>Модель: {model}"
            LLM-->>Bot: JSON с извлечёнными данными
            Bot->>Bot: merge_extracted_answer() → обновить модель
            Bot->>DB: Сохранить обновлённую модель
        else Пользователь пропускает
            Bot->>Bot: Перейти к следующему вопросу
        end
    end

    Note over User,Pub: === Фаза 3: Генерация AS-IS ===

    Note over Bot,LLM: LLM Call 3: generator.txt
    Bot->>LLM: system: generator.txt<br/>user: "Процесс: {name}<br/>Модель AS-IS: {model_json}"
    LLM-->>Bot: JSON {title, goal, stages_html, metrics_html, pain_points_html...}

    Note over Bot,LLM: LLM Call 4: mermaid.txt
    Bot->>LLM: system: mermaid.txt<br/>user: "Процесс: {name}<br/>Модель: {model_json}"
    LLM-->>Bot: Mermaid flowchart TD код
    Bot->>Bot: sanitize_mermaid() — убрать кавычки, спецсимволы

    Bot->>Pub: publish_page(token, narrative, mermaid_code)
    Pub->>Pub: Jinja2 render asis_page.html
    Pub->>Pub: WeasyPrint → PDF (опционально)
    Pub-->>Bot: URL страницы
    Bot->>DB: Сохранить published_page
    Bot->>User: Ссылка на AS-IS страницу + PDF

    Note over User,Pub: === Фаза 4: Возможности автоматизации ===

    Note over Bot,LLM: LLM Call 5: opportunities.txt
    Bot->>LLM: system: opportunities.txt<br/>user: "Процесс: {name}<br/>Модель AS-IS: {model_json}"
    LLM-->>Bot: JSON {opportunities: [{title, stage_id, type, problem, description, expected_benefit}]}
    Bot->>DB: Сохранить automation_opportunities

    Bot->>User: Список возможностей (multi-select UI)
    User->>Bot: Выбрать/отклонить возможности
    Bot->>DB: Обновить статусы (SELECTED/REJECTED)
    Bot->>Bot: Процесс → READY_FOR_TOBE
```

---

## 5. Детали промтов (Prompts)

### Таблица LLM-вызовов

| # | Файл промта | Сервис | Вход | Выход | Цель |
|---|-------------|--------|------|-------|------|
| 1 | `extractor.txt` | `extractor.py` | Имя процесса + тексты интервью + существующая модель (опц.) | JSON: goal, summary, triggers, stages[], roles, systems, artifacts, metrics, pain_points, handoffs | Извлечь структурированную AS-IS модель из свободного текста |
| 2 | `gap_detector.txt` | `gap_detector.py` | Имя процесса + модель AS-IS (JSON) | JSON: completeness_score (0-1), gaps[] с вопросами | Оценить полноту модели, найти пробелы |
| 2a | `clarification_questions.txt` | `clarification.py` | Имя процесса + модель AS-IS (JSON) | JSON: questions[] (5 категорий, include flag, suggestions) | Сгенерировать до 5 уточняющих вопросов в фиксированном порядке |
| 2b | `answer_extractor.txt` | `clarification.py` | field_type + вопрос + ответ пользователя + модель | JSON: извлечённые значения по типу поля | Извлечь структурированные данные из свободного ответа |
| 3 | `generator.txt` | `generator.py` | Имя процесса + модель AS-IS (JSON) | JSON: HTML-фрагменты (title, goal, stages_html, metrics_html, ...) | Сгенерировать нарративное описание процесса |
| 4 | `mermaid.txt` | `mermaid.py` | Имя процесса + модель (JSON) | Mermaid flowchart TD код | Визуализация процесса в виде блок-схемы |
| 5 | `opportunities.txt` | `opportunities.py` | Имя процесса + модель AS-IS (JSON) | JSON: opportunities[] (title, type, problem, description, expected_benefit) | Предложить возможности автоматизации |

### Порядок уточняющих вопросов (Clarification Flow)

```mermaid
graph TD
    Q1{1. Операции/шаги — полный ли список?}
    Q2{2. Метрики — KPI/SLA для этапов без метрик}
    Q3{3. Роли — кто выполняет этапы без owner_role}
    Q4{4. Системы — какие инструменты для этапов без systems}
    Q5{5. Артефакты — документы на входе/выходе}
    DONE[Генерация AS-IS]

    Q1 -->|include=true → спросить| Q2
    Q1 -->|include=false → пропустить| Q2
    Q2 -->|include=true → спросить| Q3
    Q2 -->|include=false → пропустить| Q3
    Q3 --> Q4
    Q4 --> Q5
    Q5 --> DONE

    style Q1 fill:#e1f5fe
    style Q2 fill:#f3e5f5
    style Q3 fill:#e8f5e9
    style Q4 fill:#fff3e0
    style Q5 fill:#fce4ec
```

---

## 6. База данных — ER-диаграмма

```mermaid
erDiagram
    COMPANIES {
        int id PK
        string name
        datetime created_at
    }

    PROCESSES {
        int id PK
        int company_id FK
        string name
        enum status "CREATED|INTERVIEW_IN_PROGRESS|CLARIFICATION_IN_PROGRESS|ASIS_READY|ASIS_PUBLISHED|AUTOMATION_SELECTION_IN_PROGRESS|READY_FOR_TOBE"
        datetime created_at
        datetime updated_at
    }

    RESPONDENTS {
        int id PK
        int telegram_user_id UK
        string display_name
        string role_label
        int invited_by FK
        datetime created_at
    }

    INTERVIEW_SESSIONS {
        int id PK
        int process_id FK
        int respondent_id FK
        string token UK "32 chars"
        enum state "STARTED|AWAITING_INITIAL_RESPONSE|PROCESSING_INPUT|AWAITING_FOLLOWUP_ANSWER|PAUSED|COMPLETED"
        datetime started_at
        datetime last_activity_at
        datetime completed_at
    }

    RAW_INPUTS {
        int id PK
        int session_id FK
        string message_type "text|voice|audio"
        int telegram_message_id
        text raw_text
        string file_ref
        text transcript_text
        datetime created_at
    }

    ASIS_MODELS {
        int id PK
        int process_id FK_UK
        int version
        text goal
        text summary
        json triggers
        json inputs
        json outputs
        json stages "id, name, description, owner_role, systems, inputs, outputs, artifacts, metrics, sla, pain_points, handoff_to"
        json roles
        json systems
        json artifacts
        json metrics
        json pain_points
        json handoffs
        float completeness_score "0.0-1.0"
        datetime generated_at
    }

    GAPS {
        int id PK
        int process_id FK
        string stage_id
        enum field_type "ROLES|SYSTEMS|ARTIFACTS|METRICS|TRIGGER|OUTPUT|SLA_TIMING|HANDOFF|DECISION_POINT|GOAL|INPUT|PAIN_POINTS"
        text question_text
        float confidence_score
        enum status "PENDING|ANSWERED|SKIPPED"
        int answer_ref FK
        datetime created_at
    }

    AUTOMATION_OPPORTUNITIES {
        int id PK
        int process_id FK
        string stage_id
        string title
        enum opp_type "AI|RULE_BASED|INTEGRATION|ANALYTICS|MONITORING"
        text problem
        text description
        text expected_benefit
        enum status "PROPOSED|SELECTED|REJECTED|SKIPPED"
        datetime created_at
    }

    PUBLISHED_PAGES {
        int id PK
        int process_id FK
        string token UK "32 chars"
        int asis_version
        text mermaid_code
        text narrative_html
        string html_url
        string pdf_path
        datetime created_at
    }

    COMPANIES ||--o{ PROCESSES : "has"
    PROCESSES ||--o{ INTERVIEW_SESSIONS : "has"
    PROCESSES ||--o| ASIS_MODELS : "has one"
    PROCESSES ||--o{ GAPS : "has"
    PROCESSES ||--o{ AUTOMATION_OPPORTUNITIES : "has"
    PROCESSES ||--o{ PUBLISHED_PAGES : "has"
    RESPONDENTS ||--o{ INTERVIEW_SESSIONS : "participates"
    RESPONDENTS ||--o{ RESPONDENTS : "invited_by"
    INTERVIEW_SESSIONS ||--o{ RAW_INPUTS : "has"
    RAW_INPUTS ||--o{ GAPS : "answer_ref"
```

---

## 7. Структура JSON модели AS-IS (asis_models.stages)

```mermaid
graph TD
    MODEL[AS-IS Model]
    MODEL --> GOAL[goal: string]
    MODEL --> SUMMARY[summary: string]
    MODEL --> TRIGGERS[triggers: string array]
    MODEL --> INPUTS[inputs: string array]
    MODEL --> OUTPUTS[outputs: string array]
    MODEL --> STAGES[stages: Stage array]
    MODEL --> ROLES[roles: string array]
    MODEL --> SYSTEMS_TOP[systems: string array]
    MODEL --> ARTIFACTS_TOP[artifacts: string array]
    MODEL --> METRICS_TOP[metrics: string array]
    MODEL --> PAIN_TOP[pain_points: string array]
    MODEL --> HANDOFFS[handoffs: string array]

    STAGES --> STAGE[Stage Object]
    STAGE --> SID[id: stage_N]
    STAGE --> SNAME[name: string]
    STAGE --> SDESC[description: string]
    STAGE --> SROLE[owner_role: string]
    STAGE --> SSYS[systems: string array]
    STAGE --> SINP[inputs: string array]
    STAGE --> SOUT[outputs: string array]
    STAGE --> SART[artifacts: string array]
    STAGE --> SMET[metrics: string array]
    STAGE --> SSLA[sla: string]
    STAGE --> SPAIN[pain_points: string array]
    STAGE --> SHAND[handoff_to: string]
```

---

## 8. Обработка входящих сообщений (Message Routing)

```mermaid
flowchart TD
    MSG[Входящее сообщение Telegram]

    MSG --> IS_CMD{Команда /start?}
    IS_CMD -->|Да| START[start_handler — показать меню процессов]

    IS_CMD -->|Нет| IS_CALLBACK{Callback query — кнопка?}
    IS_CALLBACK -->|Да| CALLBACKS[callbacks.py — роутинг по callback_data]

    IS_CALLBACK -->|Нет| CHECK_STATE{Проверка состояния чата}

    CHECK_STATE -->|awaiting_process_name| CREATE[Создать процесс с указанным именем]

    CHECK_STATE -->|clarification_in_progress| CLAR[clarification handler — обработать ответ на вопрос]

    CHECK_STATE -->|interview| INTERVIEW[interview handler]

    INTERVIEW --> IS_VOICE{Тип сообщения?}
    IS_VOICE -->|voice/audio| WHISPER[Whisper API → транскрипция]
    WHISPER --> SAVE_INPUT
    IS_VOICE -->|text| SAVE_INPUT[Сохранить raw_input в БД]
    IS_VOICE -->|document| SAVE_DOC[Сохранить file_ref в БД]

    SAVE_INPUT --> EXTRACT[LLM Call 1 — извлечь модель]
    SAVE_DOC --> EXTRACT
    EXTRACT --> GAP[LLM Call 2 — обнаружить пробелы]
    GAP --> SCORE{completeness_score >= threshold?}

    SCORE -->|Нет + вопросы есть| START_CLAR[Начать 5-Step Clarification]
    SCORE -->|Да| GEN_ASIS[Генерировать AS-IS]

    CALLBACKS --> CB_TYPE{callback_data prefix}
    CB_TYPE -->|proc_| PROC_DETAIL[Детали процесса]
    CB_TYPE -->|page_| PAGE_NAV[Навигация по страницам]
    CB_TYPE -->|skip_q| SKIP_Q[Пропустить вопрос]
    CB_TYPE -->|suggest_| SUGGEST[Выбрать подсказку как ответ]
    CB_TYPE -->|opp_toggle_| OPP_TOGGLE[Toggle выбора возможности]
    CB_TYPE -->|opp_confirm| OPP_CONFIRM[Подтвердить выбор → READY_FOR_TOBE]
```

---

## 9. Стек технологий

```mermaid
graph TB
    subgraph "Frontend — Telegram"
        TG[Telegram Bot API]
        INLINE[Inline Keyboards — кнопки]
        DEEP[Deep Links — приглашения]
    end

    subgraph "Backend — Python async"
        PTB[python-telegram-bot 21+]
        ASYNCIO[asyncio event loop]
        AIOHTTP[aiohttp HTTP server]
    end

    subgraph "AI/ML"
        GPT[OpenAI GPT-5.4 — Chat Completions]
        WHISPER[OpenAI Whisper-1 — Speech-to-Text]
    end

    subgraph "Data"
        SA[SQLAlchemy 2.0 async]
        SQLITE[aiosqlite — SQLite driver]
        PYDANTIC[Pydantic 2.0 — валидация]
    end

    subgraph "Publishing"
        JINJA[Jinja2 — шаблоны HTML]
        WEASY[WeasyPrint — HTML→PDF]
        MERMAID_JS[Mermaid.js — диаграммы в браузере]
    end

    TG --> PTB
    PTB --> ASYNCIO
    ASYNCIO --> AIOHTTP
    ASYNCIO --> SA
    SA --> SQLITE
    ASYNCIO --> GPT
    ASYNCIO --> WHISPER
    JINJA --> WEASY
```

---

## 10. UX-принципы

| Принцип | Описание |
|---------|----------|
| **One-message editing** | Бот редактирует одно сообщение вместо отправки новых — чистый чат |
| **Auto-delete user messages** | Сообщения пользователя удаляются после обработки |
| **Progress bar** | Анимированный прогресс при LLM-вызовах (▓░░░░ → ▓▓▓▓▓) |
| **Typewriter effect** | Постепенный вывод транскрипции голоса |
| **Pagination** | 5 процессов на страницу с кнопками навигации |
| **Suggestions** | Кнопки-подсказки для ответов на уточняющие вопросы |
| **Multi-select** | Чекбоксы для выбора возможностей автоматизации |
