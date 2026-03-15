# SPEC — AI Business Operating System (AI BOS)

---

## 1. Feature Context

| Section | Fill In |
|---------|---------|
| **Feature** | AI Business Operating System (AI BOS) |
| **Description (Goal / Scope)** | Единое рабочее пространство (workspace OS), объединяющее управление файлами, задачами и AI-ассистента в одном React-интерфейсе с персистентным хранением данных в БД. |
| **Client** | Команды и индивидуальные пользователи, работающие с документами, задачами и AI-инструментами |
| **Problem** | Разрозненные инструменты (файловые менеджеры, таск-трекеры, чаты с AI) снижают продуктивность; данные теряются при перезагрузке, нет единой точки входа |
| **Solution** | React SPA с тёмной темой, иерархическим файловым деревом, Markdown-редактором, дашбордом задач и контекстным AI-чатом; PostgreSQL для персистентности; REST API на бэкенде |
| **Metrics** | Время от открытия приложения до первого действия < 2 с; 0 потерь данных при перезагрузке; latency API < 200 мс (p95) |

---

## 2. User Stories and Use Cases

---

### User Story 1 — Управление файлами и папками

| Field | Fill In |
|-------|---------|
| **Role** | Пользователь рабочего пространства |
| **User Story ID** | US-1 |
| **User Story** | As a пользователь, I want to создавать, просматривать и редактировать файлы и папки в иерархическом дереве, so that я могу организовать рабочие документы в одном месте |
| **UX / User Flow** | Sidebar (260 px, слева) → дерево папок/файлов → клик по файлу → открытие вкладки в Editor → редактирование → сохранение |

#### Use Case (+ Edges) BDD 1

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-1.1 |
| **Given** | Пользователь находится в приложении, sidebar отображает дерево workspace |
| **When** | Пользователь кликает на файл в дереве |
| **Then** | Файл открывается в центральной панели Editor; добавляется вкладка; view переключается на `file` |
| **Input** | Путь к файлу (массив строк, напр. `["Проекты", "AI BOS", "README.md"]`) |
| **Output** | Содержимое файла отображается в Editor; вкладка добавлена в `openTabs` |
| **State** | `view = 'file'`, `selectedPath = [...]`, `openTabs` обновлён |

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-1 | Система должна отображать иерархическое дерево файлов и папок в Sidebar с иконками (📁 папки, 📝 .md, 📄 прочие) |
| FR-2 | Система должна поддерживать открытие файла по клику с созданием вкладки в Editor |
| FR-3 | Система должна сохранять дерево workspace в БД и загружать при старте сессии |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-1 | Дерево файлов должно рендериться за < 100 мс при 500 узлах |
| NFR-2 | Переключение между вкладками — без перезагрузки страницы (SPA) |
| NFR-3 | Данные workspace сохраняются в PostgreSQL и не теряются при перезагрузке браузера |

#### Use Case (+ Edges) BDD 2

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-1.2 |
| **Given** | Пользователь находится в Sidebar, выбрана папка |
| **When** | Пользователь нажимает кнопку «+ файл» или «+ папка» и вводит имя |
| **Then** | Новый файл/папка создаётся в дереве, сохраняется в БД |
| **Input** | Родительский путь + имя нового элемента |
| **Output** | Обновлённое дерево с новым узлом |
| **State** | `workspace` обновлён; БД синхронизирована |

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-4 | Система должна поддерживать создание файла через inline-форму с подтверждением по Enter и отменой по Escape |
| FR-5 | Система должна поддерживать создание папки с аналогичной inline-формой |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-4 | Создание файла/папки — ответ API < 200 мс |
| NFR-5 | Валидация имени: запрет спецсимволов (`/`, `\`, `..`), макс. 255 символов |

---

### User Story 2 — Редактирование документов с Markdown

| Field | Fill In |
|-------|---------|
| **Role** | Пользователь-автор документов |
| **User Story ID** | US-2 |
| **User Story** | As a автор, I want to редактировать файлы с поддержкой Markdown-рендеринга, so that я могу создавать форматированные документы без сторонних редакторов |
| **UX / User Flow** | Клик на файл → Editor (view mode, Markdown) → кнопка «Редактировать» → textarea → «Сохранить» / «Отмена» |

#### Use Case (+ Edges) BDD 1

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-2.1 |
| **Given** | Файл открыт в Editor в режиме просмотра |
| **When** | Пользователь нажимает «Редактировать», вносит изменения и нажимает «Сохранить» |
| **Then** | Содержимое файла обновляется в workspace и сохраняется в БД; Editor возвращается в view mode |
| **Input** | Новый текст файла (string) |
| **Output** | Обновлённый Markdown-рендер в Editor |
| **State** | `editing = false`, `workspace[path].content` обновлён |

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-6 | Editor должен рендерить Markdown: заголовки (h1–h3), **bold**, *italic*, `inline code`, таблицы, списки, чекбоксы (✓/☐) |
| FR-7 | Режим редактирования — textarea с текущим содержимым; кнопки «Сохранить» и «Отмена» |
| FR-8 | Хлебные крошки (breadcrumb) отображают текущий путь к файлу |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-6 | Markdown-рендеринг выполняется на клиенте без обращения к серверу |
| NFR-7 | Максимальный размер файла для редактирования — 1 МБ |

#### Use Case (+ Edges) BDD 2

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-2.2 |
| **Given** | Открыто несколько вкладок в Editor |
| **When** | Пользователь закрывает вкладку (×) или переключается на другую |
| **Then** | При закрытии — вкладка удаляется; при переключении — контент меняется без потери данных |
| **Input** | Индекс вкладки (close) / путь вкладки (switch) |
| **Output** | Обновлённый список вкладок и отображение выбранного файла |
| **State** | `openTabs` обновлён; `selectedPath` обновлён при switch |

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-9 | Tab bar отображает все открытые файлы; активная вкладка выделена |
| FR-10 | Закрытие вкладки не удаляет файл; если закрыта последняя — переход на home |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-8 | Переключение вкладок < 50 мс |
| NFR-9 | Поддержка до 20 одновременно открытых вкладок |

---

### User Story 3 — Управление задачами (Dashboard)

| Field | Fill In |
|-------|---------|
| **Role** | Менеджер задач |
| **User Story ID** | US-3 |
| **User Story** | As a пользователь, I want to создавать, фильтровать и управлять задачами на дашборде, so that я могу отслеживать прогресс работы |
| **UX / User Flow** | Home view → Dashboard → карточки задач с фильтрами (Все / В работе / Готово / Ожидание) → управление статусом → удаление |

#### Use Case (+ Edges) BDD 1

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-3.1 |
| **Given** | Пользователь на главной странице (home view), Dashboard отображает список задач |
| **When** | Пользователь выбирает фильтр «В работе» |
| **Then** | Отображаются только задачи со статусом `running` |
| **Input** | Фильтр: `'all' | 'running' | 'done' | 'pending'` |
| **Output** | Отфильтрованный список карточек задач |
| **State** | Фильтр применён на клиенте; `tasks` в store не изменён |

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-11 | Dashboard отображает карточки задач с полями: title, status (done/running/pending), timestamp (HH:MM), type (LLM/MCP/Code) |
| FR-12 | Фильтры-пилюли: «Все», «В работе», «Готово», «Ожидание»; активный фильтр выделен цветом |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-10 | Фильтрация выполняется на клиенте мгновенно (< 50 мс) |
| NFR-11 | Задачи хранятся в БД; при перезагрузке — полное восстановление |

---

### User Story 4 — AI-чат с контекстом

| Field | Fill In |
|-------|---------|
| **Role** | Пользователь, работающий с AI-ассистентом |
| **User Story ID** | US-4 |
| **User Story** | As a пользователь, I want to общаться с AI-ассистентом в контексте текущего файла, so that я могу получать релевантные ответы и автоматически создавать задачи из запросов |
| **UX / User Flow** | Правая панель (flex: 2) → индикатор контекста (текущий файл) → ввод сообщения → отправка → ответ AI → авто-создание задачи |

#### Use Case (+ Edges) BDD 1

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-4.1 |
| **Given** | Пользователь открыл файл и видит чат в правой панели |
| **When** | Пользователь вводит сообщение и нажимает «Отправить» |
| **Then** | Сообщение добавляется в чат; AI отвечает; создаётся задача на Dashboard |
| **Input** | Текст сообщения (string); контекст — `selectedPath` |
| **Output** | Новое сообщение user + ответ AI в `chatHistory`; новая задача в `tasks` |
| **State** | `chatHistory` += 2 записи; `tasks` += 1 запись со статусом `running` |

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-13 | Чат отображает историю сообщений с разделением по ролям (user/ai) и соответствующей стилизацией |
| FR-14 | Индикатор контекста показывает имя текущего открытого файла |
| FR-15 | Каждое сообщение пользователя автоматически создаёт задачу типа «LLM» со статусом `running` |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-12 | История чата сохраняется в БД и восстанавливается при перезагрузке |
| NFR-13 | Авто-скролл к последнему сообщению |

---

## 3. Architecture / Solution

### 3.1 Client Side

| Area | Fill In |
|------|---------|
| **Client Type** | Web UI (React SPA) |
| **User Entry Points** | URL приложения → загрузка SPA → Home (Dashboard + Welcome) |
| **Main Screens** | **Home** (Welcome + Dashboard), **File View** (Sidebar + Editor + Chat) |
| **Input / Output Format** | Input: клики, текст, клавиатурные шорткаты (Enter/Escape). Output: рендер UI, Markdown, карточки задач, сообщения чата |

### 3.2 Backend Services

| Area | Fill In |
|------|---------|
| **Service Name** | `ai-bos-api` |
| **Responsibility** | CRUD workspace (файлы/папки), CRUD задач, хранение чата, проксирование запросов к LLM |
| **Business Logic** | Валидация имён файлов; управление иерархией workspace; автосоздание задач из чат-сообщений; фильтрация задач |

**API / Contract**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/workspace` | GET | Получить полное дерево workspace |
| `/api/workspace/file` | POST | Создать файл |
| `/api/workspace/folder` | POST | Создать папку |
| `/api/workspace/file` | PUT | Обновить содержимое файла |
| `/api/workspace/file` | DELETE | Удалить файл |
| `/api/tasks` | GET | Получить список задач (с фильтром по статусу) |
| `/api/tasks` | POST | Создать задачу |
| `/api/tasks/:id` | PATCH | Обновить статус задачи |
| `/api/tasks/:id` | DELETE | Удалить задачу |
| `/api/chat` | GET | Получить историю чата |
| `/api/chat` | POST | Отправить сообщение (→ ответ AI) |

**Request Schema (примеры)**

```json
// POST /api/workspace/file
{
  "parentPath": ["Проекты", "AI BOS"],
  "name": "notes.md",
  "content": ""
}

// POST /api/tasks
{
  "title": "Проанализировать данные",
  "type": "LLM",
  "status": "running"
}

// POST /api/chat
{
  "text": "Проанализируй этот файл",
  "context": ["Проекты", "AI BOS", "README.md"]
}
```

**Response Schema (примеры)**

```json
// GET /api/workspace
{
  "workspace": {
    "Проекты": {
      "_type": "folder",
      "_open": true,
      "AI BOS": {
        "_type": "folder",
        "_open": false,
        "README.md": { "_type": "file", "content": "# AI BOS\n..." }
      }
    }
  }
}

// POST /api/chat → response
{
  "reply": "Файл содержит описание проекта...",
  "task": { "id": 42, "title": "Проанализируй этот файл", "status": "running", "type": "LLM", "ts": "14:30" }
}
```

**Error Handling**

| HTTP Code | Описание |
|-----------|----------|
| 400 | Невалидный запрос (некорректное имя файла, пустой путь) |
| 404 | Файл / задача не найдены |
| 409 | Конфликт (файл с таким именем уже существует) |
| 500 | Внутренняя ошибка сервера |

### 3.3 Data Architecture and Flows

**Main Entities (ER)**

```
┌──────────────┐       ┌──────────────┐
│   workspace  │       │    tasks     │
├──────────────┤       ├──────────────┤
│ id (PK)      │       │ id (PK)      │
│ parent_id(FK)│──┐    │ title        │
│ name         │  │    │ status       │  (done | running | pending)
│ type         │  │    │ type         │  (LLM | MCP | Code)
│ content      │  │    │ created_at   │
│ is_open      │  │    └──────────────┘
│ created_at   │  │
│ updated_at   │  │    ┌──────────────┐
└──────────────┘  │    │ chat_messages│
       ▲          │    ├──────────────┤
       └──────────┘    │ id (PK)      │
      (self-ref)       │ role         │  (user | ai)
                       │ text         │
                       │ context_path │
                       │ created_at   │
                       └──────────────┘
```

**Relationships (ER)**

| Связь | Описание |
|-------|----------|
| `workspace.parent_id → workspace.id` | Самоссылка: папка содержит файлы и подпапки |
| `chat_messages` — независимая сущность | Хранит историю с контекстом пути |
| `tasks` — независимая сущность | Могут создаваться из чата или вручную |

**Data Flow (DFD)**

```
[React SPA] ──HTTP/JSON──► [REST API (ai-bos-api)] ──SQL──► [PostgreSQL]
     │                            │
     │◄──── JSON responses ◄──────┘
     │
     ├─► Sidebar: GET /api/workspace
     ├─► Editor:  PUT /api/workspace/file
     ├─► Dashboard: GET/POST/PATCH/DELETE /api/tasks
     └─► Chat: GET/POST /api/chat ──► [LLM Provider] (будущая интеграция)
```

**Input Sources**

| Источник | Данные |
|----------|--------|
| Пользователь (UI) | Текст файлов, имена файлов/папок, сообщения чата, управление задачами |
| LLM Provider (API) | Ответы AI-ассистента |
| БД (PostgreSQL) | Персистентное хранение всех сущностей |

### 3.4 Infrastructure

| Resource | Описание |
|----------|----------|
| **Frontend** | Vite dev server (dev) / Nginx (prod), статические файлы React SPA |
| **Backend** | Node.js / Python (FastAPI), REST API сервер |
| **Database** | PostgreSQL 15+ |
| **Reverse Proxy** | Nginx — раздача SPA + проксирование `/api/*` на бэкенд |

---

## 4. Work Plan

### Mapping: Use Case → Tasks

| Use Case | Task ID | Task | Dependencies | DoD |
|----------|---------|------|--------------|-----|
| UC-1.1 | T-1 | Реализовать API и БД для workspace (чтение дерева, открытие файла) | — | GET /api/workspace возвращает полное дерево из БД; фронт загружает workspace при старте |
| UC-1.2 | T-2 | Реализовать создание файлов и папок через API | T-1 | POST создаёт узел в БД; Sidebar отображает новый узел без перезагрузки |
| UC-2.1 | T-3 | Реализовать сохранение файлов через API | T-1 | PUT обновляет content в БД; данные не теряются при F5 |
| UC-2.2 | T-4 | Интегрировать управление вкладками с персистентностью | T-1 | Открытые вкладки восстанавливаются из БД/localStorage |
| UC-3.1 | T-5 | Реализовать CRUD задач через API + БД | — | Задачи создаются, фильтруются, обновляются, удаляются; данные в PostgreSQL |
| UC-4.1 | T-6 | Реализовать API чата с сохранением истории | T-5 | Сообщения сохраняются в БД; задача создаётся автоматически; история восстанавливается |

---

## 5. Detailed Task Breakdown

---

### Task 1

| Field | Fill In |
|-------|---------|
| **Task ID** | T-1 |
| **Related Use Case** | UC-1.1 |
| **Task Description** | Создать схему БД для workspace и API эндпоинт для получения дерева файлов |
| **Dependencies** | — |
| **DoD** | GET /api/workspace возвращает JSON-дерево из PostgreSQL; фронт загружает данные при монтировании App |

**Subtasks**

| Subtask ID | Description | Dependencies | Acceptance Criteria |
|------------|-------------|--------------|---------------------|
| ST-1 | Создать таблицу `workspace_nodes` (id, parent_id, name, type, content, is_open, created_at, updated_at) | — | Миграция применяется; таблица создана; self-referencing FK работает |
| ST-2 | Реализовать GET /api/workspace — рекурсивная сборка дерева из БД | ST-1 | Эндпоинт возвращает вложенную JSON-структуру, совместимую с типом `Workspace` на фронте |
| ST-3 | Подключить фронт к API: загрузка workspace в useStore при старте | ST-2 | При загрузке приложения Sidebar отображает дерево из БД |

---

### Task 2

| Field | Fill In |
|-------|---------|
| **Task ID** | T-2 |
| **Related Use Case** | UC-1.2 |
| **Task Description** | Реализовать создание файлов и папок через API с сохранением в БД |
| **Dependencies** | T-1 |
| **DoD** | Создание файла/папки через Sidebar сохраняется в БД; повторная загрузка показывает новые узлы |

**Subtasks**

| Subtask ID | Description | Dependencies | Acceptance Criteria |
|------------|-------------|--------------|---------------------|
| ST-4 | Реализовать POST /api/workspace/file и POST /api/workspace/folder | T-1 | Эндпоинты создают записи в `workspace_nodes`; возвращают созданный узел |
| ST-5 | Подключить createFile/createFolder в useStore к API вызовам | ST-4 | Inline-форма в Sidebar отправляет запрос; при успехе — обновляет локальный state |

---

### Task 3

| Field | Fill In |
|-------|---------|
| **Task ID** | T-3 |
| **Related Use Case** | UC-2.1 |
| **Task Description** | Реализовать сохранение содержимого файлов через API |
| **Dependencies** | T-1 |
| **DoD** | Кнопка «Сохранить» в Editor отправляет PUT; после F5 — контент сохранён |

**Subtasks**

| Subtask ID | Description | Dependencies | Acceptance Criteria |
|------------|-------------|--------------|---------------------|
| ST-6 | Реализовать PUT /api/workspace/file (обновление content) | T-1 | Эндпоинт обновляет `content` в `workspace_nodes`; возвращает 200 |
| ST-7 | Реализовать DELETE /api/workspace/file | T-1 | Эндпоинт удаляет узел и дочерние; возвращает 200 |
| ST-8 | Подключить saveContent в useStore к PUT API | ST-6 | При «Сохранить» — fetch PUT; при ошибке — уведомление пользователю |

---

### Task 4

| Field | Fill In |
|-------|---------|
| **Task ID** | T-4 |
| **Related Use Case** | UC-2.2 |
| **Task Description** | Интегрировать управление вкладками с персистентностью |
| **Dependencies** | T-1 |
| **DoD** | Открытые вкладки сохраняются в localStorage; при перезагрузке — восстанавливаются |

**Subtasks**

| Subtask ID | Description | Dependencies | Acceptance Criteria |
|------------|-------------|--------------|---------------------|
| ST-9 | Сохранять openTabs и selectedPath в localStorage при каждом изменении | T-1 | JSON-массив вкладок записывается в localStorage |
| ST-10 | Восстанавливать вкладки при инициализации useStore | ST-9 | При загрузке SPA — открытые вкладки и выбранный файл восстановлены |

---

### Task 5

| Field | Fill In |
|-------|---------|
| **Task ID** | T-5 |
| **Related Use Case** | UC-3.1 |
| **Task Description** | Реализовать полный CRUD задач через API с хранением в PostgreSQL |
| **Dependencies** | — |
| **DoD** | Задачи создаются, читаются, обновляются, удаляются через API; Dashboard работает с реальными данными из БД |

**Subtasks**

| Subtask ID | Description | Dependencies | Acceptance Criteria |
|------------|-------------|--------------|---------------------|
| ST-11 | Создать таблицу `tasks` (id, title, status, type, created_at) и миграцию | — | Таблица создана; enum для status и type |
| ST-12 | Реализовать CRUD эндпоинты: GET/POST/PATCH/DELETE /api/tasks | ST-11 | Все операции работают; GET поддерживает query-параметр `?status=` |
| ST-13 | Подключить Dashboard и useStore к API задач | ST-12 | createTask, updateTaskStatus, deleteTask — вызывают API; Dashboard загружает задачи при старте |

---

### Task 6

| Field | Fill In |
|-------|---------|
| **Task ID** | T-6 |
| **Related Use Case** | UC-4.1 |
| **Task Description** | Реализовать API чата с сохранением истории в БД и автосозданием задач |
| **Dependencies** | T-5 |
| **DoD** | Сообщения чата сохраняются в БД; при отправке — создаётся задача; история восстанавливается при перезагрузке |

**Subtasks**

| Subtask ID | Description | Dependencies | Acceptance Criteria |
|------------|-------------|--------------|---------------------|
| ST-14 | Создать таблицу `chat_messages` (id, role, text, context_path, created_at) | — | Таблица создана; role — enum (user, ai) |
| ST-15 | Реализовать GET /api/chat и POST /api/chat | ST-14 | GET возвращает историю; POST сохраняет сообщение, генерирует ответ-заглушку, создаёт задачу |
| ST-16 | Подключить Chat компонент и useStore к API | ST-15 | sendMessage → POST /api/chat; chatHistory загружается при старте |
