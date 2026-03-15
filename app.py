"""
AI Business Operating System (AI BOS) — Workspace OS
Единая среда работы человека и ИИ на Streamlit.
"""

import streamlit as st
import json
from datetime import datetime

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AI BOS · Workspace OS",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Initialise session state
# ---------------------------------------------------------------------------

# Workspace tree — default demo data
DEFAULT_WORKSPACE: dict = {
    "Проекты": {
        "_type": "folder",
        "AI BOS": {
            "_type": "folder",
            "PRD.md": {"_type": "file", "content": "# PRD — AI Business Operating System\n\nОписание продукта…"},
            "Архитектура.md": {"_type": "file", "content": "# Архитектура\n\n## Компоненты\n- Frontend (Streamlit)\n- Backend API\n- LLM Service"},
            "Бэклог.md": {"_type": "file", "content": "# Бэклог\n\n- [ ] MVP интерфейса\n- [ ] Интеграция с LLM\n- [ ] Система задач"},
        },
        "Маркетинг": {
            "_type": "folder",
            "Стратегия.md": {"_type": "file", "content": "# Маркетинговая стратегия\n\n## Каналы\n1. SEO\n2. Content marketing\n3. Community"},
        },
    },
    "Документы": {
        "_type": "folder",
        "Заметки.md": {"_type": "file", "content": "# Заметки\n\nРабочие заметки и идеи…"},
        "Шаблон отчёта.md": {"_type": "file", "content": "# Отчёт\n\n## Период: …\n## Результаты\n…"},
    },
    "Данные": {
        "_type": "folder",
        "KPI Q1.md": {"_type": "file", "content": "# KPI Q1 2026\n\n| Метрика | План | Факт |\n|---------|------|------|\n| Revenue | 100k | 95k  |\n| Users   | 10k  | 12k  |"},
    },
}

if "workspace" not in st.session_state:
    st.session_state.workspace = DEFAULT_WORKSPACE

if "selected_path" not in st.session_state:
    st.session_state.selected_path = None

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "tasks" not in st.session_state:
    st.session_state.tasks = [
        {"id": 1, "title": "Сгенерировать PRD", "status": "done", "ts": "14:02"},
        {"id": 2, "title": "Проанализировать KPI", "status": "running", "ts": "14:15"},
        {"id": 3, "title": "Подготовить отчёт", "status": "pending", "ts": "—"},
    ]

if "next_task_id" not in st.session_state:
    st.session_state.next_task_id = 4


# ---------------------------------------------------------------------------
# Helper: traverse workspace tree by path
# ---------------------------------------------------------------------------

def _get_node(path: list[str]) -> dict | None:
    """Return the node at *path* inside the workspace tree."""
    node = st.session_state.workspace
    for part in path:
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def _set_content(path: list[str], content: str):
    """Update content of a file node."""
    node = st.session_state.workspace
    for part in path[:-1]:
        node = node[part]
    node[path[-1]]["content"] = content


# ---------------------------------------------------------------------------
# CSS — custom layout styling
# ---------------------------------------------------------------------------

st.markdown("""
<style>
/* Global spacing */
.block-container { padding-top: 1rem !important; padding-bottom: 0 !important; }

/* Sidebar tree items */
div[data-testid="stSidebar"] .stButton > button {
    text-align: left !important;
    padding: 0.2rem 0.5rem !important;
    font-size: 0.85rem !important;
    background: transparent !important;
    border: none !important;
    color: #ccc !important;
    width: 100% !important;
    border-radius: 4px !important;
}
div[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(79,139,249,0.15) !important;
    color: #fff !important;
}

/* Chat messages */
.chat-user { background: #1e2a3a; border-radius: 8px; padding: 0.6rem 0.8rem; margin: 0.3rem 0; }
.chat-ai   { background: #1a2520; border-radius: 8px; padding: 0.6rem 0.8rem; margin: 0.3rem 0; }

/* Task bar */
.task-bar { display: flex; gap: 0.7rem; overflow-x: auto; padding: 0.4rem 0; }
.task-chip {
    display: inline-flex; align-items: center; gap: 0.35rem;
    padding: 0.3rem 0.7rem; border-radius: 16px; font-size: 0.78rem;
    white-space: nowrap;
}
.chip-done    { background: #1a3a2a; color: #6fcf97; }
.chip-running { background: #2a2a1a; color: #f2c94c; }
.chip-pending { background: #1a1a2a; color: #828282; }

/* Bottom bar border */
.bottom-bar { border-top: 1px solid #2a2d35; padding-top: 0.5rem; margin-top: 0.5rem; }

/* Selected sidebar item highlight */
div[data-testid="stSidebar"] .selected-item > button {
    background: rgba(79,139,249,0.25) !important;
    color: #4F8BF9 !important;
    font-weight: 600 !important;
}

/* Editor area */
.editor-header {
    display: flex; align-items: center; gap: 0.5rem;
    padding-bottom: 0.5rem; border-bottom: 1px solid #2a2d35;
    margin-bottom: 0.7rem;
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# SIDEBAR — workspace tree (left panel)
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### 🗂 Workspace")

    def _render_tree(node: dict, path: list[str], depth: int = 0):
        """Recursively render the workspace tree."""
        for key, value in node.items():
            if key.startswith("_"):
                continue
            current_path = path + [key]
            path_str = "/".join(current_path)
            is_folder = isinstance(value, dict) and value.get("_type") == "folder"

            if is_folder:
                prefix = "📁" if depth > 0 else "📂"
                indent = "&nbsp;" * (depth * 4)
                st.markdown(
                    f"<div style='padding:2px 0 2px {depth * 12}px; "
                    f"font-size:0.85rem; color:#aaa;'>"
                    f"{prefix} <strong>{key}</strong></div>",
                    unsafe_allow_html=True,
                )
                _render_tree(value, current_path, depth + 1)
            else:
                is_selected = (
                    st.session_state.selected_path is not None
                    and "/".join(st.session_state.selected_path) == path_str
                )
                icon = "📝" if key.endswith(".md") else "📄"
                label = f"{icon} {key}"
                btn_type = "primary" if is_selected else "secondary"
                if st.button(label, key=f"tree_{path_str}", use_container_width=True, type=btn_type):
                    st.session_state.selected_path = current_path
                    st.rerun()

    _render_tree(st.session_state.workspace, [])

    st.divider()

    # --- Quick actions ---
    st.markdown("#### ➕ Создать")
    new_item_name = st.text_input("Имя файла / папки", key="new_item_name", label_visibility="collapsed", placeholder="Новый файл.md")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("📄 Файл", use_container_width=True):
            name = st.session_state.new_item_name.strip()
            if name:
                st.session_state.workspace.setdefault("Документы", {"_type": "folder"})
                st.session_state.workspace["Документы"][name] = {
                    "_type": "file",
                    "content": f"# {name}\n\n",
                }
                st.session_state.selected_path = ["Документы", name]
                st.rerun()
    with c2:
        if st.button("📁 Папку", use_container_width=True):
            name = st.session_state.new_item_name.strip()
            if name:
                st.session_state.workspace[name] = {"_type": "folder"}
                st.rerun()


# ---------------------------------------------------------------------------
# MAIN AREA — centre editor + right AI chat
# ---------------------------------------------------------------------------

# Title
st.markdown(
    "<h2 style='margin:0 0 0.5rem 0;'>⚙️ AI Business Operating System</h2>",
    unsafe_allow_html=True,
)

col_editor, col_chat = st.columns([3, 2], gap="medium")

# ---- Centre: Editor / Viewer --------------------------------------------------
with col_editor:
    if st.session_state.selected_path:
        node = _get_node(st.session_state.selected_path)
        file_name = st.session_state.selected_path[-1]

        if node and isinstance(node, dict) and node.get("_type") == "file":
            st.markdown(
                f"<div class='editor-header'>"
                f"<span style='font-size:1.1rem;'>📝</span>"
                f"<strong>{file_name}</strong>"
                f"<span style='color:#666; font-size:0.8rem;'>— "
                f"{'/'.join(st.session_state.selected_path[:-1])}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

            content = node.get("content", "")
            tab_view, tab_edit = st.tabs(["👁 Просмотр", "✏️ Редактирование"])

            with tab_view:
                st.markdown(content)

            with tab_edit:
                new_content = st.text_area(
                    "Редактор",
                    value=content,
                    height=400,
                    key=f"editor_{'/'.join(st.session_state.selected_path)}",
                    label_visibility="collapsed",
                )
                if st.button("💾 Сохранить", key="save_btn"):
                    _set_content(st.session_state.selected_path, new_content)
                    st.success("Сохранено!")
                    st.rerun()
        else:
            st.info("Выберите файл в дереве слева.")
    else:
        # Welcome screen
        st.markdown("""
        ### 👋 Добро пожаловать в Workspace OS

        **Выберите файл** в дереве слева, чтобы начать работу.

        Возможности:
        - 📁 **Навигация** по проектам и документам
        - ✏️ **Редактирование** содержимого
        - 🤖 **AI-ассистент** для генерации и анализа
        - 📊 **Отслеживание задач** в реальном времени
        """)

# ---- Right: AI Chat -----------------------------------------------------------
with col_chat:
    st.markdown("#### 🤖 AI-ассистент")

    # Context indicator
    if st.session_state.selected_path:
        ctx_label = st.session_state.selected_path[-1]
        st.caption(f"Контекст: **{ctx_label}**")
    else:
        st.caption("Контекст: *общий*")

    # Chat history display
    chat_container = st.container(height=380)
    with chat_container:
        if not st.session_state.chat_history:
            st.markdown(
                "<div style='color:#666; text-align:center; padding-top:3rem;'>"
                "Начните диалог — задайте вопрос или поставьте задачу.</div>",
                unsafe_allow_html=True,
            )
        for msg in st.session_state.chat_history:
            css_class = "chat-user" if msg["role"] == "user" else "chat-ai"
            icon = "👤" if msg["role"] == "user" else "🤖"
            st.markdown(
                f"<div class='{css_class}'>{icon} {msg['text']}</div>",
                unsafe_allow_html=True,
            )

    # Chat input
    user_input = st.chat_input("Задайте вопрос или поставьте задачу…")
    if user_input:
        st.session_state.chat_history.append({"role": "user", "text": user_input})

        # --- Demo AI response (placeholder) ---
        context_note = ""
        if st.session_state.selected_path:
            node = _get_node(st.session_state.selected_path)
            if node and isinstance(node, dict):
                context_note = f"\n\n*(Контекст: {st.session_state.selected_path[-1]})*"

        ai_response = (
            f"Принято! Я обработаю ваш запрос: «{user_input}».{context_note}\n\n"
            f"_Подключите API-ключ для полноценных ответов от LLM._"
        )
        st.session_state.chat_history.append({"role": "ai", "text": ai_response})

        # Add a demo task
        st.session_state.tasks.append({
            "id": st.session_state.next_task_id,
            "title": user_input[:50] + ("…" if len(user_input) > 50 else ""),
            "status": "running",
            "ts": datetime.now().strftime("%H:%M"),
        })
        st.session_state.next_task_id += 1
        st.rerun()


# ---------------------------------------------------------------------------
# BOTTOM BAR — task pipeline / status
# ---------------------------------------------------------------------------

st.divider()

bcol_label, bcol_tasks = st.columns([1, 6])

with bcol_label:
    st.markdown("**📊 Задачи**")

with bcol_tasks:
    # Render task chips as HTML
    chips_html = '<div class="task-bar">'
    status_icons = {"done": "✅", "running": "⏳", "pending": "⏸️"}
    status_classes = {"done": "chip-done", "running": "chip-running", "pending": "chip-pending"}

    for task in st.session_state.tasks:
        icon = status_icons.get(task["status"], "❓")
        cls = status_classes.get(task["status"], "chip-pending")
        chips_html += (
            f'<span class="task-chip {cls}">'
            f'{icon} {task["title"]} '
            f'<span style="opacity:0.6;">({task["ts"]})</span>'
            f'</span>'
        )
    chips_html += '</div>'
    st.markdown(chips_html, unsafe_allow_html=True)

# Task management expander
with st.expander("🔧 Управление задачами"):
    tcol1, tcol2, tcol3 = st.columns([3, 1, 1])
    with tcol1:
        new_task_title = st.text_input("Новая задача", key="new_task", label_visibility="collapsed", placeholder="Описание задачи…")
    with tcol2:
        new_task_status = st.selectbox("Статус", ["pending", "running", "done"], key="new_task_status", label_visibility="collapsed")
    with tcol3:
        if st.button("➕ Добавить", use_container_width=True):
            if new_task_title.strip():
                st.session_state.tasks.append({
                    "id": st.session_state.next_task_id,
                    "title": new_task_title.strip(),
                    "status": new_task_status,
                    "ts": datetime.now().strftime("%H:%M"),
                })
                st.session_state.next_task_id += 1
                st.rerun()

    # Task list with status toggles
    if st.session_state.tasks:
        for i, task in enumerate(st.session_state.tasks):
            tc1, tc2, tc3 = st.columns([4, 1, 1])
            with tc1:
                icon = status_icons.get(task["status"], "❓")
                st.markdown(f"{icon} **{task['title']}** `{task['ts']}`")
            with tc2:
                new_status = st.selectbox(
                    "Статус",
                    ["pending", "running", "done"],
                    index=["pending", "running", "done"].index(task["status"]),
                    key=f"task_status_{task['id']}",
                    label_visibility="collapsed",
                )
                if new_status != task["status"]:
                    st.session_state.tasks[i]["status"] = new_status
                    st.rerun()
            with tc3:
                if st.button("🗑", key=f"del_task_{task['id']}"):
                    st.session_state.tasks.pop(i)
                    st.rerun()
