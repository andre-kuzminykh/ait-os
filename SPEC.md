# SPEC — AI Business Operating System (AI BOS)

---

## 1. Feature Context

| Section | Fill In |
|---------|---------|
| **Feature** | AI Business Operating System (AI BOS) |
| **Description (Goal / Scope)** | Единая рабочая платформа, объединяющая мультимодальный хаб нейросетей, версионное файловое хранилище (память), управление контекстом с drag & drop, Markdown-редактор с задачами и автоматизацией, и AI-генерацию Streamlit-приложений. React SPA + FastAPI + PostgreSQL. |
| **Client** | Команды и индивидуальные пользователи, работающие с AI-инструментами, документами, данными и приложениями |
| **Problem** | 1) Нет единого интерфейса для работы с разными AI-моделями (текст, картинки, код). 2) Файлы теряются, нет версионности. 3) Нет удобного управления контекстом для AI. 4) Создание AI-приложений требует ручного кодирования. |
| **Solution** | 5 модулей в одном SPA: мультимодальный AI-хаб, версионная файловая память, drag & drop контекст-менеджер, редактор+задачи, AI-генератор Streamlit-приложений |
| **Metrics** | Время первого действия < 2 с; 0 потерь данных; API latency < 200 мс (p95); поддержка ≥ 3 LLM-провайдеров; генерация Streamlit-приложения < 30 с |

---

## 2. User Stories and Use Cases

---

## Категория A — Мультимодальный хаб нейросетей

### User Story 1 — Чат с выбором AI-модели

| Field | Fill In |
|-------|---------|
| **Role** | Пользователь AI-хаба |
| **User Story ID** | US-1 |
| **User Story** | As a пользователь, I want to общаться с разными AI-моделями (текст, код, картинки) через единый чат-интерфейс с выбором провайдера, so that я могу использовать лучшую модель под каждую задачу |
| **UX / User Flow** | Правая панель → селектор модели (GPT-4, Claude, Mistral, DALL-E, Stable Diffusion, Code Llama и др.) → селектор модальности (текст / изображение / код) → ввод промпта → ответ → история |

#### Use Case BDD 1 — Текстовый запрос к LLM

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-1.1 |
| **Given** | Пользователь в чате, выбрана текстовая модель (напр. Claude Sonnet) |
| **When** | Пользователь вводит текстовый промпт и нажимает «Отправить» |
| **Then** | Запрос отправляется к выбранному провайдеру; ответ отображается в чате; сообщения сохраняются в БД |
| **Input** | text (string), model_id (string), context_files (array, optional) |
| **Output** | AI-ответ (text); обновлённая история чата |
| **State** | `chatHistory` += 2 записи (user + ai); `selectedModel` не изменён |

**Edge cases:**
- Провайдер недоступен → уведомление «Модель недоступна, попробуйте другую»; сообщение сохраняется с флагом error
- Превышен rate limit → уведомление с таймером retry
- Пустой промпт → кнопка заблокирована

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-1 | Чат-интерфейс с единым полем ввода; селектор модели в хедере чата |
| FR-2 | Поддержка провайдеров: OpenAI (GPT-4, GPT-4o), Anthropic (Claude Sonnet/Opus), Mistral (Mistral Large) — как минимум 3 |
| FR-3 | Каждое сообщение хранит: роль, текст, model_id, provider, модальность, context_files, timestamp |
| FR-4 | Streaming ответов (SSE) — текст появляется по мере генерации |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-1 | Время до первого токена (TTFT) < 2 с для текстовых моделей |
| NFR-2 | История чата сохраняется в БД; восстанавливается при перезагрузке |
| NFR-3 | API-ключи провайдеров хранятся серверно в env/secrets; никогда не передаются на клиент |

#### Use Case BDD 2 — Генерация изображения

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-1.2 |
| **Given** | Пользователь в чате, выбрана модель генерации изображений (напр. DALL-E 3) |
| **When** | Пользователь вводит текстовое описание и нажимает «Отправить» |
| **Then** | Запрос отправляется к провайдеру; сгенерированное изображение отображается в чате; изображение автоматически сохраняется в память (файловое хранилище) |
| **Input** | text (string), model_id (string), params (size, style — optional) |
| **Output** | URL/blob изображения в чате; файл в хранилище |
| **State** | `chatHistory` += 2 записи; файл добавлен в `workspace` (папка «Генерации») |

**Edge cases:**
- Content policy violation → уведомление от провайдера; сообщение сохраняется с флагом `blocked`
- Таймаут генерации (> 60 с) → уведомление; возможность retry

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-5 | Поддержка генерации изображений: DALL-E 3 (OpenAI), Stable Diffusion (через API) — минимум 2 |
| FR-6 | Сгенерированное изображение отображается inline в чате (превью) с возможностью просмотра в полном размере |
| FR-7 | Автосохранение сгенерированных изображений в папку «Генерации» в файловом хранилище |
| FR-8 | Параметры генерации: размер (1024x1024 и др.), стиль (если поддерживается моделью) |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-4 | Максимальное время генерации изображения — 60 с; после — таймаут с retry |
| NFR-5 | Изображения хранятся в файловой системе сервера + метаданные в БД |

#### Use Case BDD 3 — Генерация / анализ кода

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-1.3 |
| **Given** | Пользователь в чате, выбрана модель для кода (напр. GPT-4, Claude, Code Llama) |
| **When** | Пользователь просит сгенерировать / проанализировать / исправить код |
| **Then** | AI возвращает код с подсветкой синтаксиса; кнопка «Сохранить в файл» для сохранения в память |
| **Input** | text (string), model_id (string), language (optional), context_files (optional) |
| **Output** | Код с подсветкой синтаксиса в чате; кнопка сохранения |
| **State** | `chatHistory` += 2 записи |

**Edge cases:**
- Очень длинный вывод кода (> 10 000 строк) → truncation с кнопкой «Показать полностью»
- Модель не определила язык кода → fallback на plain text
- Таймаут генерации кода (> 60 с) → уведомление; возможность retry

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-9 | Блоки кода в ответе AI — с подсветкой синтаксиса (определение языка автоматическое) |
| FR-10 | Кнопка «Сохранить в файл» на каждом блоке кода → создаёт файл в памяти |
| FR-11 | Кнопка «Вставить в редактор» → открывает файл в Editor с вставленным кодом |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-6 | Подсветка синтаксиса для ≥ 10 языков (JS, TS, Python, Go, Rust, Java, C++, SQL, HTML, CSS) |

---

## Категория B — Память с файлами (версионное хранилище)

### User Story 2 — Файловое хранилище с версионностью

| Field | Fill In |
|-------|---------|
| **Role** | Пользователь, управляющий документами |
| **User Story ID** | US-2 |
| **User Story** | As a пользователь, I want to хранить файлы в иерархическом дереве с автоматической версионностью, so that я могу откатиться к любой предыдущей версии и не бояться потерять данные |
| **UX / User Flow** | Sidebar (дерево файлов) → CRUD операции → каждое сохранение = новая версия → панель версий → откат |

#### Use Case BDD 1 — CRUD файлов и папок

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-2.1 |
| **Given** | Пользователь в Sidebar, видит дерево workspace |
| **When** | Пользователь создаёт / открывает / переименовывает / удаляет файл или папку |
| **Then** | Операция выполняется; дерево обновляется; данные сохраняются в БД |
| **Input** | Зависит от операции: parentPath + name (создание), path (открытие/удаление), path + newName (переименование) |
| **Output** | Обновлённое дерево |
| **State** | `workspace` обновлён; БД синхронизирована |

**Edge cases:**
- Дубликат имени в одной папке → ошибка 409
- Спецсимволы в имени (`/`, `\`, `..`) → ошибка валидации
- Удаление папки с дочерними → каскадное удаление с подтверждением
- Удалённый файл открыт во вкладке → вкладка автоматически закрывается
- Переименование открытого файла → вкладка и breadcrumb обновляются

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-12 | Иерархическое дерево файлов в Sidebar с иконками (📁 папки, 📝 .md, 📄 прочие, 🖼 изображения) |
| FR-13 | Создание файла/папки через inline-форму (Enter — подтверждение, Escape — отмена) |
| FR-14 | Удаление с подтверждением; каскадное удаление папок |
| FR-15 | Переименование inline (двойной клик); обновление вкладок и breadcrumb |
| FR-16 | Toggle папок (сворачивание/разворачивание); состояние сохраняется в БД |
| FR-17 | Валидация имён: запрет `/`, `\`, `..`; макс. 255 символов; уникальность в папке |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-7 | Дерево рендерится < 100 мс при 500 узлах |
| NFR-8 | CRUD операции — API response < 200 мс |
| NFR-9 | Каскадное удаление — в одной транзакции |

#### Use Case BDD 2 — Версионность файлов

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-2.2 |
| **Given** | Пользователь открыл файл в Editor |
| **When** | Пользователь сохраняет изменения |
| **Then** | Создаётся новая версия файла (snapshot предыдущего content); текущий content обновляется |
| **Input** | Новый content (string) |
| **Output** | Файл обновлён; новая запись в `file_versions` |
| **State** | `workspace[path].content` обновлён; `file_versions` += 1 запись |

**Edge cases:**
- Превышен лимит 100 версий → самая старая версия автоматически удаляется
- Сохранение без изменений (content идентичен) → версия НЕ создаётся (оптимизация)
- Файл > 1 МБ → предупреждение о размере, но версия всё равно создаётся

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-18 | Каждое сохранение файла автоматически создаёт версию (snapshot) в таблице `file_versions`; если content не изменился — версия не создаётся |
| FR-19 | Панель «История версий» в Editor: список версий с датой, номером версии и размером |
| FR-20 | Просмотр любой версии: клик по версии → содержимое отображается в read-only |
| FR-21 | Откат к версии: кнопка «Восстановить» → текущий content заменяется на content версии (при этом создаётся новая версия) |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-10 | Хранение до 100 версий на файл; при превышении — удаление самых старых |
| NFR-11 | Просмотр версии — без полной загрузки страницы (AJAX) |

---

## Категория C — Управление контекстом

### User Story 3 — Drag & Drop файлов в контекст AI-чата

| Field | Fill In |
|-------|---------|
| **Role** | Пользователь, работающий с AI |
| **User Story ID** | US-3 |
| **User Story** | As a пользователь, I want to перетаскивать файлы из памяти в контекст AI-чата и управлять этим контекстом, so that AI получает релевантную информацию для ответов |
| **UX / User Flow** | Sidebar (файлы) → drag файл → drop в зону контекста над чатом → чипсы прикреплённых файлов (с версией) → отправка сообщения с контекстом |

#### Use Case BDD 1 — Добавление файла в контекст

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-3.1 |
| **Given** | Пользователь видит Sidebar с файлами и чат в правой панели |
| **When** | Пользователь перетаскивает файл из Sidebar в зону контекста чата |
| **Then** | Файл добавляется в контекст; отображается как чипс (имя + версия + ×) |
| **Input** | file_id (int), version_id (int, optional — по умолчанию latest) |
| **Output** | Чипс файла в зоне контекста |
| **State** | `chatContext` += { file_id, version_id, name } |

**Edge cases:**
- Файл уже в контексте → игнорируется (no-op)
- Перетаскивание папки → добавляются все файлы из папки (не рекурсивно, только первый уровень)
- Удаление файла из контекста → клик по × на чипсе

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-22 | Drag & Drop из Sidebar в зону контекста чата (HTML5 Drag and Drop API) |
| FR-23 | Зона контекста отображает чипсы: имя файла + номер версии + кнопка удаления (×) |
| FR-24 | По умолчанию прикрепляется последняя версия файла; возможность выбрать конкретную версию через клик на чипсе |
| FR-25 | При отправке сообщения — содержимое прикреплённых файлов включается в промпт к AI |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-12 | Drag & Drop — отзывчивый (визуальная обратная связь < 50 мс) |
| NFR-13 | Максимум 10 файлов в контексте одновременно |
| NFR-14 | Суммарный размер контекста (все файлы) не должен превышать токен-лимит выбранной модели; предупреждение при приближении |

#### Use Case BDD 2 — Смена версии файла в контексте

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-3.2 |
| **Given** | Файл прикреплён к контексту чата как чипс |
| **When** | Пользователь кликает на чипс файла |
| **Then** | Открывается popup со списком версий; пользователь выбирает нужную версию |
| **Input** | file_id, new_version_id |
| **Output** | Чипс обновляет отображаемую версию |
| **State** | `chatContext[file_id].version_id` обновлён |

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-26 | Клик по чипсу → popup с версиями (дата, номер, размер) |
| FR-27 | Выбор версии → чипс обновляется; при следующей отправке — используется выбранная версия |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-15 | Загрузка списка версий < 200 мс |

---

## Категория D — Редактор и Задачи

### User Story 4 — Markdown-редактор

| Field | Fill In |
|-------|---------|
| **Role** | Автор документов |
| **User Story ID** | US-4 |
| **User Story** | As a автор, I want to редактировать файлы с Markdown-рендерингом и управлять вкладками, so that я могу работать с несколькими документами одновременно |
| **UX / User Flow** | Клик на файл → Editor (view mode, Markdown) → «Редактировать» → textarea → «Сохранить» / «Отмена» → версия создана |

#### Use Case BDD 1 — Редактирование и сохранение

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-4.1 |
| **Given** | Файл открыт в Editor в режиме просмотра |
| **When** | Пользователь нажимает «Редактировать», вносит изменения и нажимает «Сохранить» |
| **Then** | Content обновляется в БД; создаётся новая версия (UC-2.2); Editor возвращается в view mode |
| **Input** | Новый текст (string) |
| **Output** | Обновлённый Markdown-рендер; новая версия в истории |
| **State** | `editing = false`; content обновлён; `file_versions` += 1 |

**Edge cases:**
- «Отмена» → откат изменений, content не меняется
- Сетевая ошибка → уведомление; данные остаются в textarea
- Закрытие вкладки с несохранёнными изменениями → диалог «Есть несохранённые изменения»

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-28 | Markdown-рендер: h1–h3, **bold**, *italic*, `inline code`, ```code blocks``` с подсветкой, таблицы, списки, чекбоксы (✓/☐) |
| FR-29 | Режим редактирования: textarea + кнопки «Сохранить» / «Отмена» |
| FR-30 | Breadcrumb с текущим путём к файлу |
| FR-31 | При ошибке сохранения → уведомление; данные не теряются |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-16 | Markdown-рендер — клиентский, без обращения к серверу |
| NFR-17 | Макс. размер файла — 5 МБ; предупреждение при > 1 МБ |

#### Use Case BDD 2 — Управление вкладками

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-4.2 |
| **Given** | Открыто несколько вкладок |
| **When** | Пользователь закрывает (×) или переключает вкладку |
| **Then** | Закрытие — вкладка удаляется; переключение — отображается другой файл |
| **Input** | Индекс / путь вкладки |
| **Output** | Обновлённый tab bar |
| **State** | `openTabs` обновлён; `selectedPath` обновлён; localStorage синхронизирован |

**Edge cases:**
- Закрытие последней вкладки → переход на home
- Закрытие/переключение в режиме редактирования → диалог «Несохранённые изменения»

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-32 | Tab bar с активной вкладкой; кнопка × для закрытия |
| FR-33 | Последняя вкладка закрыта → переход на home view |
| FR-34 | Диалог подтверждения при несохранённых изменениях |
| FR-35 | Открытые вкладки сохраняются в localStorage; восстанавливаются при перезагрузке |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-18 | Переключение вкладок < 50 мс |
| NFR-19 | Поддержка до 20 открытых вкладок |

---

### User Story 5 — Задачи и автоматизация

| Field | Fill In |
|-------|---------|
| **Role** | Менеджер задач |
| **User Story ID** | US-5 |
| **User Story** | As a пользователь, I want to создавать задачи вручную и автоматически (из чата), фильтровать их, менять статус и удалять, so that я могу отслеживать прогресс и автоматизировать рутинные операции |
| **UX / User Flow** | Home → Dashboard → карточки задач → фильтры → управление. Чат → автосоздание задачи при каждом сообщении. |

#### Use Case BDD 1 — Фильтрация задач

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-5.1 |
| **Given** | Dashboard отображает список задач |
| **When** | Пользователь выбирает фильтр (Все / В работе / Готово / Ожидание) |
| **Then** | Отображаются только задачи с выбранным статусом |
| **Input** | Фильтр: `'all' | 'running' | 'done' | 'pending'` |
| **Output** | Отфильтрованный список |
| **State** | Клиентская фильтрация; `tasks` не изменён |

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-36 | Карточки задач: title, status (done/running/pending), timestamp, type (LLM/MCP/Code/Manual) |
| FR-37 | Фильтры-пилюли; активный выделен |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-20 | Фильтрация < 50 мс на клиенте |
| NFR-21 | Задачи — в БД; восстанавливаются при перезагрузке |

#### Use Case BDD 2 — CRUD задач

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-5.2 |
| **Given** | Пользователь на Dashboard |
| **When** | Пользователь создаёт / меняет статус / удаляет задачу |
| **Then** | Операция выполняется через API; карточка обновляется |
| **Input** | Зависит: title+type (создание), id+status (смена), id (удаление) |
| **Output** | Обновлённый Dashboard |
| **State** | `tasks` обновлён; БД синхронизирована |

**Edge cases:**
- Пустой title → валидация
- Смена на тот же статус → no-op
- Автоматическое создание задачи из чата → type = «LLM», status = «running»

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-38 | Ручное создание: форма с title (обязат., макс. 500 символов) и type (LLM/MCP/Code/Manual) |
| FR-39 | Смена статуса: раскрываемая секция на карточке; цветовые бейджи (done — зелёный, running — синий, pending — серый) |
| FR-40 | Удаление задачи: кнопка в секции управления; без подтверждения |
| FR-41 | Автоматическое создание задачи при каждом сообщении в чате (type = LLM, status = running) |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-22 | CRUD операции — API < 200 мс |

---

## Категория E — Генерация Streamlit-приложений через AI

### User Story 6 — AI-генерация Streamlit-приложений

| Field | Fill In |
|-------|---------|
| **Role** | Пользователь, создающий приложения |
| **User Story ID** | US-6 |
| **User Story** | As a пользователь, I want to описать приложение текстом в чате и получить работающее Streamlit-приложение с превью, so that я могу быстро создавать data-приложения без ручного кодирования |
| **UX / User Flow** | Чат → описание приложения → AI генерирует Streamlit-код → код сохраняется в файл → система запускает Streamlit → iframe с превью → итеративное редактирование через чат или Editor |

#### Use Case BDD 1 — Генерация приложения из описания

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-6.1 |
| **Given** | Пользователь в чате, выбрана текстовая модель (GPT-4 / Claude) |
| **When** | Пользователь описывает приложение (напр. «Создай дашборд для визуализации CSV-файлов с графиками») |
| **Then** | AI генерирует Streamlit-код; код сохраняется в файл `apps/<name>/app.py`; Streamlit-процесс запускается; iframe с превью отображается |
| **Input** | text-описание приложения (string); model_id |
| **Output** | Файл `app.py` в хранилище; запущенный Streamlit-процесс; iframe в UI |
| **State** | `workspace` += новый файл; `streamlit_apps` += запись; процесс запущен |

**Edge cases:**
- AI генерирует невалидный код → Streamlit показывает ошибку в iframe; пользователь может исправить через чат («Исправь ошибку: ...»)
- Порт занят → автоматический выбор свободного порта
- Пользователь закрывает превью → процесс Streamlit останавливается

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-42 | AI генерирует полный Streamlit-код на основе текстового описания пользователя. Режим генерации активируется через кнопку «Создать приложение» в чате (отдельный от обычного чата intent) |
| FR-43 | Сгенерированный код автоматически сохраняется в файловое хранилище: `apps/<app_name>/app.py` |
| FR-44 | Бэкенд запускает Streamlit-процесс (`streamlit run app.py --server.port <port>`) на уникальном порту |
| FR-45 | Iframe в UI отображает работающее Streamlit-приложение |
| FR-46 | Панель управления приложением: кнопки «Остановить», «Перезапустить», «Редактировать код» |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-23 | Генерация кода < 30 с |
| NFR-24 | Максимум 3 одновременно запущенных Streamlit-приложения (ограничение ресурсов) |
| NFR-25 | Каждый Streamlit-процесс изолирован (отдельный порт, отдельная директория) |
| NFR-26 | При остановке/закрытии приложения — процесс корректно завершается (SIGTERM) |
| NFR-26a | Безопасность: Streamlit-процессы запускаются с ограничением ресурсов (CPU: 1 ядро, RAM: 512 МБ, timeout: 30 мин); запрет доступа к файловой системе за пределами своей директории; whitelist Python-пакетов |

#### Use Case BDD 2 — Итеративное редактирование через чат

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-6.2 |
| **Given** | Streamlit-приложение запущено и отображается в iframe |
| **When** | Пользователь пишет в чат: «Добавь фильтр по дате» / «Измени цветовую схему» |
| **Then** | AI модифицирует код; файл обновляется (новая версия); Streamlit автоматически перезагружается (hot reload); iframe обновляется |
| **Input** | Текст изменения (string); текущий код файла (в контексте) |
| **Output** | Обновлённый код; перезагрузка превью |
| **State** | `file_versions` += 1; Streamlit hot-reload |

**Edge cases:**
- AI ломает код → ошибка в iframe; пользователь может попросить «Откати к предыдущей версии»
- Hot reload не срабатывает → кнопка «Перезапустить» вручную

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-47 | AI модифицирует существующий код на основе инструкции; diff показывается в чате |
| FR-48 | Файл обновляется → Streamlit hot reload → iframe обновляется автоматически |
| FR-49 | Возможность откатить код к предыдущей версии через панель версий (UC-2.2) |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-27 | Hot reload Streamlit < 5 с после сохранения файла |

#### Use Case BDD 3 — Управление запущенными приложениями

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-6.3 |
| **Given** | Одно или несколько Streamlit-приложений запущены |
| **When** | Пользователь открывает панель «Мои приложения» |
| **Then** | Отображается список запущенных приложений с статусом, портом, кнопками управления |
| **Input** | — |
| **Output** | Список приложений: name, status (running/stopped), port, actions |
| **State** | Чтение из `streamlit_apps` |

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-50 | Панель «Мои приложения» на Dashboard: список всех приложений (запущенных и остановленных) |
| FR-51 | Действия: «Открыть» (iframe), «Остановить», «Запустить», «Удалить» |
| FR-52 | При удалении приложения — процесс останавливается, файлы остаются в хранилище |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-28 | Статус приложений обновляется по polling каждые 5 с |

---

### User Story 7 — Навигация Home ↔ File View

| Field | Fill In |
|-------|---------|
| **Role** | Пользователь |
| **User Story ID** | US-7 |
| **User Story** | As a пользователь, I want to переключаться между Dashboard и файловым видом, so that я могу быстро перемещаться между задачами и документами |
| **UX / User Flow** | Кнопка «Home» в Sidebar → Dashboard. Клик на файл → File View. |

#### Use Case BDD 1 — Навигация

| Field | Fill In |
|-------|---------|
| **Use Case ID** | UC-7.1 |
| **Given** | Пользователь в File View |
| **When** | Нажимает «Home» |
| **Then** | Центральная панель → Dashboard + Welcome; вкладки сохраняются |
| **Input** | Клик |
| **Output** | Dashboard |
| **State** | `view = 'home'`; `openTabs` не изменён |

**Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| FR-53 | Кнопка Home всегда доступна в Sidebar |
| FR-54 | При возврате — вкладки сохраняются |

**Non-Functional Requirements**

| Req ID | Requirement |
|--------|-------------|
| NFR-29 | Переключение < 100 мс |

---

## 3. Architecture / Solution

### 3.1 Client Side

| Area | Fill In |
|------|---------|
| **Client Type** | Web UI (React 19 SPA, Vite 8, TypeScript) |
| **User Entry Points** | URL → SPA → Home (Dashboard + Welcome + Мои приложения) |
| **Main Screens** | **Home** (Dashboard + Welcome + Мои приложения), **File View** (Sidebar + Editor + Chat + Version Panel), **App Preview** (iframe Streamlit) |
| **Input / Output Format** | Input: клики, текст, drag & drop, клавиатурные шорткаты. Output: Markdown-рендер, AI-ответы (text + images + code), Streamlit iframe, карточки задач |

### 3.2 Backend Services

| Area | Fill In |
|------|---------|
| **Service Name** | `ai-bos-api` |
| **Technology** | Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2 |
| **Responsibility** | CRUD workspace, версионность файлов, CRUD задач, чат с роутингом к LLM-провайдерам, управление Streamlit-процессами |

**API / Contract**

| Endpoint | Method | Description |
|----------|--------|-------------|
| **Workspace** | | |
| `/api/workspace` | GET | Полное дерево workspace |
| `/api/workspace/file` | POST | Создать файл |
| `/api/workspace/folder` | POST | Создать папку |
| `/api/workspace/file` | PUT | Обновить content (+ автосоздание версии) |
| `/api/workspace/file` | DELETE | Удалить файл/папку (каскадно) |
| `/api/workspace/node/:id/rename` | PATCH | Переименовать |
| `/api/workspace/node/:id/toggle` | PATCH | Toggle open/closed |
| **Версии** | | |
| `/api/files/:id/versions` | GET | Список версий файла (?limit, ?offset) |
| `/api/files/:id/versions/:vid` | GET | Содержимое конкретной версии |
| `/api/files/:id/versions/:vid/restore` | POST | Откат к версии |
| **Задачи** | | |
| `/api/tasks` | GET | Список задач (?status, ?limit, ?offset) |
| `/api/tasks` | POST | Создать задачу |
| `/api/tasks/:id` | PATCH | Обновить статус |
| `/api/tasks/:id` | DELETE | Удалить задачу |
| **Чат** | | |
| `/api/chat` | GET | История чата (?limit, ?offset) |
| `/api/chat` | POST | Отправить сообщение → ответ AI + авто-задача |
| `/api/chat/stream` | POST | SSE streaming ответа |
| **AI Модели** | | |
| `/api/models` | GET | Список доступных моделей с capabilities |
| **Streamlit Apps** | | |
| `/api/apps` | GET | Список приложений |
| `/api/apps` | POST | Создать + запустить приложение |
| `/api/apps/:id` | DELETE | Удалить приложение |
| `/api/apps/:id/start` | POST | Запустить |
| `/api/apps/:id/stop` | POST | Остановить |
| `/api/apps/:id/restart` | POST | Перезапустить |

**Адресация**: Workspace CRUD использует `path[]` (массив строк) для адресации по пути; PATCH rename/toggle использует `:id` (числовой ID узла из БД). GET /api/workspace возвращает `id` для каждого узла, чтобы фронт мог использовать оба подхода.

**Request Schema (ключевые)**

```json
// POST /api/workspace/file
{
  "parentPath": ["Проекты", "AI BOS"],
  "name": "notes.md",
  "content": ""
}

// POST /api/workspace/folder
{
  "parentPath": ["Проекты"],
  "name": "Новая папка"
}

// DELETE /api/workspace/file
{
  "path": ["Проекты", "AI BOS", "notes.md"]
}

// PATCH /api/workspace/node/:id/rename
{
  "newName": "README.md"
}

// PATCH /api/workspace/node/:id/toggle
// пустое тело — сервер инвертирует is_open

// POST /api/chat
{
  "text": "Проанализируй этот файл",
  "modelId": "claude-sonnet-4-20250514",
  "contextFiles": [
    { "fileId": 15, "versionId": 3 },
    { "fileId": 22, "versionId": null }   // null = latest
  ]
}

// POST /api/chat/stream (SSE)
{
  "text": "Напиши функцию сортировки",
  "modelId": "gpt-4",
  "contextFiles": []
}

// PUT /api/workspace/file
{
  "path": ["Проекты", "AI BOS", "README.md"],
  "content": "# Updated\n..."
}
// → автоматически создаёт запись в file_versions

// POST /api/files/:id/versions/:vid/restore
// пустое тело — сервер берёт content из версии

// POST /api/apps
{
  "name": "csv-dashboard",
  "description": "Дашборд для CSV",
  "code": "import streamlit as st\n..."
}

// GET /api/models → 200
{
  "models": [
    { "id": "claude-sonnet-4-20250514", "provider": "anthropic", "name": "Claude Sonnet", "capabilities": ["text", "code"], "maxTokens": 200000 },
    { "id": "gpt-4", "provider": "openai", "name": "GPT-4", "capabilities": ["text", "code"], "maxTokens": 128000 },
    { "id": "dall-e-3", "provider": "openai", "name": "DALL-E 3", "capabilities": ["image"], "maxTokens": null },
    { "id": "mistral-large", "provider": "mistral", "name": "Mistral Large", "capabilities": ["text", "code"], "maxTokens": 128000 }
  ]
}
```

**Response Schema (ключевые)**

```json
// GET /api/workspace → 200
{
  "workspace": {
    "Проекты": {
      "_type": "folder", "_open": true,
      "AI BOS": {
        "_type": "folder", "_open": false,
        "README.md": { "_type": "file", "id": 15, "content": "# AI BOS\n..." }
      }
    },
    "apps": {
      "_type": "folder", "_open": false,
      "csv-dashboard": {
        "_type": "folder", "_open": false,
        "app.py": { "_type": "file", "id": 30, "content": "import streamlit..." }
      }
    }
  }
}

// POST /api/workspace/file → 201
{
  "id": 15,
  "name": "notes.md",
  "type": "file",
  "content": "",
  "parentId": 3,
  "createdAt": "2026-03-15T14:30:00Z"
}

// POST /api/workspace/folder → 201
{
  "id": 16,
  "name": "Новая папка",
  "type": "folder",
  "isOpen": false,
  "parentId": 1,
  "createdAt": "2026-03-15T14:30:00Z"
}

// DELETE /api/workspace/file → 200
{
  "deleted": 3,
  "message": "Удалено 3 узла"
}

// PATCH /api/workspace/node/:id/rename → 200
{
  "id": 15,
  "name": "README.md",
  "updatedAt": "2026-03-15T14:31:00Z"
}

// POST /api/chat → 201
{
  "userMessage": { "id": 129, "role": "user", "text": "...", "modelId": "claude-sonnet-4-20250514", "contextFiles": [...], "createdAt": "..." },
  "aiMessage": { "id": 130, "role": "ai", "text": "...", "modelId": "claude-sonnet-4-20250514", "createdAt": "..." },
  "task": { "id": 44, "title": "...", "status": "running", "type": "LLM", "createdAt": "..." }
}

// GET /api/files/:id/versions → 200
{
  "versions": [
    { "id": 1, "versionNumber": 1, "size": 1024, "createdAt": "2026-03-15T10:00:00Z" },
    { "id": 2, "versionNumber": 2, "size": 1130, "createdAt": "2026-03-15T11:30:00Z" },
    { "id": 3, "versionNumber": 3, "size": 980, "createdAt": "2026-03-15T14:00:00Z" }
  ],
  "total": 3
}

// GET /api/files/:id/versions/:vid → 200
{
  "id": 2,
  "versionNumber": 2,
  "content": "# Previous content\n...",
  "size": 1130,
  "createdAt": "2026-03-15T11:30:00Z"
}

// GET /api/apps → 200
{
  "apps": [
    { "id": 1, "name": "csv-dashboard", "status": "running", "port": 8501, "fileId": 30, "createdAt": "..." },
    { "id": 2, "name": "ml-predictor", "status": "stopped", "port": null, "fileId": 35, "createdAt": "..." }
  ]
}

// Ошибки
{
  "error": "Файл с таким именем уже существует",
  "code": "CONFLICT",
  "details": { "path": ["Проекты", "AI BOS", "README.md"] }
}
```

**Error Handling**

| HTTP Code | Code | Описание |
|-----------|------|----------|
| 400 | `VALIDATION_ERROR` | Невалидный запрос |
| 404 | `NOT_FOUND` | Ресурс не найден |
| 409 | `CONFLICT` | Дубликат имени |
| 422 | `UNPROCESSABLE` | Pydantic validation error |
| 429 | `RATE_LIMITED` | Rate limit провайдера AI |
| 500 | `INTERNAL_ERROR` | Внутренняя ошибка |
| 502 | `PROVIDER_ERROR` | Ошибка AI-провайдера |
| 503 | `PROVIDER_UNAVAILABLE` | AI-провайдер недоступен |

### 3.3 Data Architecture and Flows

**Main Entities (ER)**

```
┌─────────────────────┐
│   workspace_nodes   │
├─────────────────────┤
│ id (PK, serial)     │       ┌─────────────────────┐
│ parent_id (FK→self) │──┐    │    file_versions     │
│ name (varchar 255)  │  │    ├─────────────────────┤
│ type (enum)         │  │    │ id (PK, serial)      │
│ content (text, null)│  │    │ file_id (FK→ws.id)   │──► workspace_nodes.id
│ is_open (bool)      │  │    │ version_number (int) │
│ sort_order (int)    │  │    │ content (text)       │
│ created_at (ts)     │  │    │ size (int)           │
│ updated_at (ts)     │  │    │ created_at (ts)      │
└─────────────────────┘  │    └─────────────────────┘
       ▲                 │
       └─────────────────┘    ┌─────────────────────┐
       (self-ref, CASCADE)    │       tasks          │
                              ├─────────────────────┤
┌──────────────────────┐       │ id (PK, serial)      │
│   chat_messages      │       │ title (varchar 500)  │
├──────────────────────┤       │ status (enum)        │ done|running|pending
│ id (PK, serial)      │       │ type (enum)          │ LLM|MCP|Code|Manual
│ role (enum)          │ u|ai  │ source_chat_id (FK)  │──► chat_messages.id (nullable)
│ text (text)          │       │ created_at (ts)      │
│ model_id (varchar)   │       │ updated_at (ts)      │
│ provider (varchar)   │       └─────────────────────┘
│ context_files (jsonb)│  [{fileId, versionId, name}]
│ attachments (jsonb)  │  [{type:"image"|"code", fileId, url}]
│ is_error (bool)      │  default false
│ created_at (ts)      │
│ updated_at (ts)      │       ┌─────────────────────┐
└──────────────────────┘       │   streamlit_apps     │
                              ├─────────────────────┤
┌─────────────────────┐       │ id (PK, serial)      │
│   ai_providers      │       │ name (varchar 255)   │
├─────────────────────┤       │ description (text)   │
│ id (PK, serial)     │       │ file_id (FK→ws.id)   │──► workspace_nodes.id
│ name (varchar)      │       │ port (int, nullable) │
│ provider (varchar)  │       │ status (enum)        │ running|stopped
│ capabilities (jsonb)│       │ pid (int, nullable)  │
│ max_tokens (int)    │       │ created_at (ts)      │
│ is_active (bool)    │       │ updated_at (ts)      │
│ config (jsonb)      │       └─────────────────────┘
└─────────────────────┘
```

**Relationships (ER)**

| Связь | Тип | Описание |
|-------|-----|----------|
| `workspace_nodes.parent_id → workspace_nodes.id` | self-ref FK, ON DELETE CASCADE | Папки содержат файлы и подпапки |
| `file_versions.file_id → workspace_nodes.id` | FK, ON DELETE CASCADE | Версии привязаны к файлу |
| `tasks.source_chat_id → chat_messages.id` | FK, nullable | Задачи из чата ссылаются на сообщение |
| `streamlit_apps.file_id → workspace_nodes.id` | FK, ON DELETE RESTRICT | Приложение ссылается на файл app.py; удаление файла запрещено, пока есть связанное приложение |

**Индексы**

| Таблица | Индекс | Тип |
|---------|--------|-----|
| `workspace_nodes` | `(parent_id, name)` | UNIQUE |
| `workspace_nodes` | `(parent_id, sort_order)` | B-tree |
| `file_versions` | `(file_id, version_number)` | UNIQUE |
| `file_versions` | `(file_id, created_at)` | B-tree |
| `tasks` | `(status)` | B-tree |
| `tasks` | `(created_at)` | B-tree |
| `chat_messages` | `(created_at)` | B-tree |

**Seed Data**

```
├── Проекты/
│   └── AI BOS/
│       └── README.md  ("# AI BOS\nОписание проекта...")
├── Документы/
│   └── Заметки.md     ("# Заметки\n- Первая заметка")
├── Данные/
├── Генерации/           ← для сгенерированных изображений
└── apps/                ← для Streamlit-приложений
```

**Data Flow (DFD)**

```
                                    ┌──────────────┐
                                    │  OpenAI API  │
                                    │  (GPT, DALL-E)│
                               ┌───►│              │
                               │    └──────────────┘
                               │
[React SPA] ──HTTP/JSON──► [FastAPI] ──► [Anthropic API]
     │            │SSE        │          (Claude)
     │◄───────────┘           │
     │                        ├───► [Mistral API]
     │                        │
     │                   ┌────▼────┐
     │                   │PostgreSQL│
     │                   └─────────┘
     │                        │
     │                   ┌────▼─────────┐
     │                   │ Streamlit    │
     │◄──── iframe ──────│ Processes    │
     │                   │ (ports 8501+)│
     │                   └──────────────┘
     │
     ├─► Sidebar:    workspace CRUD + toggle
     ├─► Editor:     file content + versions
     ├─► Chat:       messages + AI routing + context files
     ├─► Dashboard:  tasks CRUD + filter
     ├─► Apps:       streamlit management
     └─► Context:    drag & drop + version select
```

**Input Sources**

| Источник | Данные |
|----------|--------|
| Пользователь (UI) | Текст, файлы, drag & drop, промпты, описания приложений |
| LLM Providers | Текстовые ответы, сгенерированные изображения, код |
| PostgreSQL | Персистентное хранение всех сущностей |
| localStorage | Открытые вкладки, selectedPath |
| Streamlit | Запущенные приложения (iframe) |

### 3.4 Infrastructure

| Resource | Описание |
|----------|----------|
| **Frontend** | Vite 8 dev / Nginx prod; React SPA |
| **Backend** | Python 3.11+, FastAPI, Uvicorn (ASGI) |
| **Database** | PostgreSQL 15+ |
| **Migrations** | Alembic |
| **File Storage** | Файловая система сервера (изображения, Streamlit-код); метаданные в БД |
| **Streamlit Runtime** | Streamlit 1.30+; процессы запускаются бэкендом; порты 8501–8510 |
| **Reverse Proxy** | Nginx — SPA + `/api/*` → FastAPI + `/apps/:port/*` → Streamlit |
| **CORS** | FastAPI CORSMiddleware |
| **Environment** | `.env`: DATABASE_URL, OPENAI_API_KEY, ANTHROPIC_API_KEY, MISTRAL_API_KEY, CORS_ORIGINS |

---

## 4. Work Plan

### Mapping: Use Case → Tasks

| Use Case | Task ID | Task | Dependencies | DoD |
|----------|---------|------|--------------|-----|
| UC-2.1 | T-1 | FastAPI + БД + CRUD workspace | — | GET/POST/PUT/DELETE/PATCH workspace работают; фронт загружает дерево |
| UC-2.2 | T-2 | Версионность файлов | T-1 | Каждое сохранение → версия; список версий; просмотр; откат |
| UC-4.1, UC-4.2 | T-3 | Markdown-редактор + вкладки | T-1 | Editor рендерит Markdown; вкладки persist в localStorage; диалог unsaved changes |
| UC-5.1, UC-5.2 | T-4 | CRUD задач + Dashboard | — | Задачи CRUD через API; фильтрация; бейджи статусов |
| UC-1.1, UC-1.2, UC-1.3 | T-5 | Мультимодальный AI-хаб (чат + роутинг моделей) | T-4 | Чат с выбором модели; текст + изображения + код; SSE streaming; авто-задачи |
| UC-3.1, UC-3.2 | T-6 | Управление контекстом (drag & drop) | T-1, T-2, T-5 | Drag файлов в контекст; чипсы с версиями; контекст передаётся в промпт |
| UC-6.1, UC-6.2, UC-6.3 | T-7 | AI-генерация Streamlit-приложений | T-5, T-1, T-2 | AI генерирует код; Streamlit запускается; iframe превью; итеративное редактирование |
| UC-7.1 | T-8 | Навигация Home ↔ File View | T-1, T-3 | Переключение; вкладки сохраняются |

---

## 5. Detailed Task Breakdown

---

### Task 1

| Field | Fill In |
|-------|---------|
| **Task ID** | T-1 |
| **Related Use Case** | UC-2.1 |
| **Task Description** | Инициализация FastAPI проекта + БД + полный CRUD workspace (файлы, папки, toggle, rename) |
| **Dependencies** | — |
| **DoD** | Все workspace эндпоинты работают; фронт загружает дерево из БД при старте |

**Subtasks**

| Subtask ID | Description | Dependencies | Acceptance Criteria |
|------------|-------------|--------------|---------------------|
| ST-1 | Инициализировать FastAPI: структура проекта, SQLAlchemy async, Alembic, Pydantic, CORS, Uvicorn | — | `uvicorn` стартует; `/docs` → Swagger |
| ST-2 | Создать таблицу `workspace_nodes` + UNIQUE(parent_id, name) + seed data | ST-1 | Миграция; seed; таблица с тестовыми данными |
| ST-3 | GET /api/workspace — рекурсивная сборка дерева | ST-2 | JSON-дерево, совместимое с типом `Workspace` на фронте |
| ST-4 | POST file/folder, PUT file, DELETE file, PATCH rename, PATCH toggle | ST-2 | Все операции работают; валидация; 409 при дубликатах; CASCADE при удалении |
| ST-5 | Подключить фронт (useStore) к API workspace | ST-3, ST-4 | Sidebar загружает дерево; CRUD через API; toggle/rename через API |

---

### Task 2

| Field | Fill In |
|-------|---------|
| **Task ID** | T-2 |
| **Related Use Case** | UC-2.2 |
| **Task Description** | Реализовать версионность файлов |
| **Dependencies** | T-1 |
| **DoD** | Каждое сохранение → версия; GET список версий; GET содержимое версии; POST откат |

**Subtasks**

| Subtask ID | Description | Dependencies | Acceptance Criteria |
|------------|-------------|--------------|---------------------|
| ST-6 | Создать таблицу `file_versions` + UNIQUE(file_id, version_number) | T-1 | Миграция применяется |
| ST-7 | Модифицировать PUT /api/workspace/file: перед обновлением — snapshot в file_versions | ST-6 | Каждый PUT создаёт версию; version_number автоинкремент |
| ST-8 | GET /api/files/:id/versions (список) и GET /api/files/:id/versions/:vid (содержимое) | ST-6 | Список с пагинацией; содержимое конкретной версии |
| ST-9 | POST /api/files/:id/versions/:vid/restore — откат | ST-7 | Откат заменяет content и создаёт новую версию |
| ST-10 | UI: панель «История версий» в Editor; просмотр; кнопка «Восстановить» | ST-8, ST-9 | Панель отображает версии; read-only просмотр; откат работает |

---

### Task 3

| Field | Fill In |
|-------|---------|
| **Task ID** | T-3 |
| **Related Use Case** | UC-4.1, UC-4.2 |
| **Task Description** | Markdown-редактор + управление вкладками + localStorage persist |
| **Dependencies** | T-1 |
| **DoD** | Editor рендерит Markdown; вкладки в localStorage; диалог unsaved changes |

**Subtasks**

| Subtask ID | Description | Dependencies | Acceptance Criteria |
|------------|-------------|--------------|---------------------|
| ST-11 | Editor: Markdown-рендер (h1-h3, bold, italic, code, tables, lists, checkboxes, code blocks с подсветкой) | T-1 | Все элементы Markdown рендерятся корректно |
| ST-12 | Editor: режим редактирования (textarea + Save/Cancel); breadcrumb | T-1 | Переключение view↔edit; breadcrumb показывает путь |
| ST-13 | Сохранение через PUT API (→ автоверсия); уведомление при ошибке | T-1 | Save → PUT; ошибка → toast; данные не теряются |
| ST-14 | Вкладки: open/close/switch; persist в localStorage; диалог unsaved changes | T-1 | Вкладки восстанавливаются; диалог при unsaved |

---

### Task 4

| Field | Fill In |
|-------|---------|
| **Task ID** | T-4 |
| **Related Use Case** | UC-5.1, UC-5.2 |
| **Task Description** | Полный CRUD задач + Dashboard |
| **Dependencies** | — |
| **DoD** | Задачи CRUD через API; Dashboard с фильтрами; бейджи статусов; форма создания |

**Subtasks**

| Subtask ID | Description | Dependencies | Acceptance Criteria |
|------------|-------------|--------------|---------------------|
| ST-15 | Таблица `tasks` + миграция + enum status/type | — | Таблица создана |
| ST-16 | GET /api/tasks (?status, ?limit, ?offset); POST; PATCH :id; DELETE :id | ST-15 | CRUD работает; фильтрация по status; пагинация |
| ST-17 | Dashboard UI: карточки, фильтры-пилюли, секция управления, форма «+ Задача» | ST-16 | Всё подключено к API; авто-обновление |

---

### Task 5

| Field | Fill In |
|-------|---------|
| **Task ID** | T-5 |
| **Related Use Case** | UC-1.1, UC-1.2, UC-1.3 |
| **Task Description** | Мультимодальный AI-хаб: чат с роутингом моделей, SSE streaming, генерация изображений, подсветка кода |
| **Dependencies** | T-4 |
| **DoD** | Чат с выбором модели; текстовые ответы + streaming; генерация изображений; блоки кода с подсветкой; автосоздание задач |

**Subtasks**

| Subtask ID | Description | Dependencies | Acceptance Criteria |
|------------|-------------|--------------|---------------------|
| ST-18 | Таблица `chat_messages` (role, text, model_id, provider, context_files jsonb, attachments jsonb, is_error) + таблица `ai_providers` | — | Миграции; seed с провайдерами |
| ST-19 | GET /api/models — список доступных моделей с capabilities | ST-18 | Возвращает модели с provider, capabilities, maxTokens |
| ST-20 | POST /api/chat — роутинг к провайдеру (OpenAI/Anthropic/Mistral); сохранение; авто-задача | ST-18, T-4 | Запрос уходит к выбранному провайдеру; 2 сообщения + задача сохранены |
| ST-21 | POST /api/chat/stream — SSE streaming ответа | ST-20 | Текст появляется по мере генерации; финальное сообщение сохраняется |
| ST-22 | Интеграция с провайдерами изображений (DALL-E, Stable Diffusion); автосохранение в «Генерации» | ST-20 | Изображение генерируется; отображается в чате; файл в хранилище |
| ST-23 | UI: Chat с селектором модели; inline images; code blocks с подсветкой; кнопки «Сохранить в файл» / «Вставить в редактор» | ST-19, ST-21, ST-22 | Всё подключено; streaming работает; изображения inline |

---

### Task 6

| Field | Fill In |
|-------|---------|
| **Task ID** | T-6 |
| **Related Use Case** | UC-3.1, UC-3.2 |
| **Task Description** | Управление контекстом: drag & drop файлов из Sidebar в чат; выбор версии |
| **Dependencies** | T-1, T-2, T-5 |
| **DoD** | Drag файлов в контекст; чипсы с версиями; popup выбора версии; контекст включается в промпт |

**Subtasks**

| Subtask ID | Description | Dependencies | Acceptance Criteria |
|------------|-------------|--------------|---------------------|
| ST-24 | HTML5 Drag and Drop: draggable на элементах Sidebar; drop zone над Chat input | T-1 | Файлы перетаскиваются; визуальный feedback |
| ST-25 | Зона контекста: чипсы (имя + версия + ×); максимум 10 файлов | ST-24 | Чипсы отображаются; удаление по ×; дубликаты игнорируются |
| ST-26 | Popup выбора версии: клик на чипс → список версий → выбор | T-2, ST-25 | Версия на чипсе обновляется |
| ST-27 | Интеграция с POST /api/chat: contextFiles включаются в промпт; предупреждение при превышении токен-лимита | ST-25, T-5 | Контекст передаётся; AI учитывает файлы; предупреждение работает |

---

### Task 7

| Field | Fill In |
|-------|---------|
| **Task ID** | T-7 |
| **Related Use Case** | UC-6.1, UC-6.2, UC-6.3 |
| **Task Description** | AI-генерация Streamlit-приложений: генерация кода, запуск процесса, iframe превью, итеративное редактирование, управление |
| **Dependencies** | T-5, T-1, T-2 |
| **DoD** | AI генерирует Streamlit-код по описанию; код сохраняется; Streamlit запускается; iframe; итерация через чат; панель «Мои приложения» |

**Subtasks**

| Subtask ID | Description | Dependencies | Acceptance Criteria |
|------------|-------------|--------------|---------------------|
| ST-28 | Таблица `streamlit_apps` (name, file_id, port, status, pid) + миграция | T-1 | Таблица создана |
| ST-29 | POST /api/apps: сохранить код в файл, запустить Streamlit-процесс на свободном порту | ST-28 | Процесс запускается; порт выделяется автоматически; статус = running |
| ST-30 | POST /api/apps/:id/stop, /start, /restart, DELETE | ST-29 | Stop → SIGTERM; Start → новый процесс; Restart → stop+start; Delete → stop + обновление статуса |
| ST-31 | GET /api/apps — список приложений с статусами | ST-28 | Возвращает список; реальный статус процессов |
| ST-32 | Интеграция AI: при описании приложения в чате → AI генерирует код → auto POST /api/apps | T-5, ST-29 | Описание → код → файл → запуск → iframe |
| ST-33 | UI: iframe для превью; панель управления (Stop/Restart/Edit); панель «Мои приложения» на Dashboard | ST-29, ST-31 | Iframe отображает Streamlit; кнопки работают; Dashboard показывает список |
| ST-34 | Итеративное редактирование: пользователь пишет изменения в чат → AI обновляет код → file save → Streamlit hot reload | ST-32, T-2 | Изменение через чат обновляет код; версия создаётся; hot reload |
| ST-35 | Nginx проксирование /apps/:port/* → localhost:port | ST-29 | Iframe загружает Streamlit через reverse proxy |

---

### Task 8

| Field | Fill In |
|-------|---------|
| **Task ID** | T-8 |
| **Related Use Case** | UC-7.1 |
| **Task Description** | Навигация Home ↔ File View |
| **Dependencies** | T-1, T-3 |
| **DoD** | Кнопка Home → Dashboard; клик на файл → File View; вкладки сохраняются |

**Subtasks**

| Subtask ID | Description | Dependencies | Acceptance Criteria |
|------------|-------------|--------------|---------------------|
| ST-36 | goHome() в useStore; привязка к кнопке Home в Sidebar | T-1 | Переключение < 100 мс; вкладки не теряются |
| ST-37 | Интеграция Dashboard (задачи + Мои приложения) на Home view | T-4, T-7 | Home показывает Dashboard + список приложений |
