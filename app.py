"""
AI Business Operating System (AI BOS) — Workspace OS
Единая среда работы человека и ИИ на Streamlit.
"""

from __future__ import annotations

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
if "open_tabs" not in st.session_state:
    st.session_state.open_tabs = []
if "editing" not in st.session_state:
    st.session_state.editing = False

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_node(path: list[str]) -> dict | None:
    node = st.session_state.workspace
    for part in path:
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def _set_content(path: list[str], content: str):
    node = st.session_state.workspace
    for part in path[:-1]:
        node = node[part]
    node[path[-1]]["content"] = content


def _collect_files(node: dict, path: list[str]) -> list[list[str]]:
    results: list[list[str]] = []
    for key, value in node.items():
        if key.startswith("_"):
            continue
        current = path + [key]
        if isinstance(value, dict) and value.get("_type") == "folder":
            results.extend(_collect_files(value, current))
        elif isinstance(value, dict) and value.get("_type") == "file":
            results.append(current)
    return results


def _open_file(path: list[str]):
    st.session_state.selected_path = path
    st.session_state.editing = False
    if tuple(path) not in [tuple(t) for t in st.session_state.open_tabs]:
        st.session_state.open_tabs.append(path)


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

st.markdown("""
<style>
/* Global */
.block-container { padding-top: 0.8rem !important; padding-bottom: 0 !important; }

/* Sidebar file buttons */
div[data-testid="stSidebar"] .stButton > button {
    text-align: left !important;
    padding: 0.15rem 0.5rem !important;
    font-size: 0.82rem !important;
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
.chat-user {
    background: #1e2a3a; border-radius: 8px;
    padding: 0.5rem 0.7rem; margin: 0.25rem 0;
    font-size: 0.88rem;
}
.chat-ai {
    background: #1a2520; border-radius: 8px;
    padding: 0.5rem 0.7rem; margin: 0.25rem 0;
    font-size: 0.88rem;
}

/* Tab bar */
.tab-bar {
    display: flex; gap: 2px; overflow-x: auto;
    border-bottom: 2px solid #2a2d35; padding: 0;
    margin-bottom: 0.6rem; scrollbar-width: thin;
}
.tab-item {
    display: inline-flex; align-items: center; gap: 0.3rem;
    padding: 0.4rem 0.9rem; font-size: 0.8rem;
    border: 1px solid transparent; border-bottom: none;
    border-radius: 6px 6px 0 0; cursor: default;
    background: transparent; color: #666; white-space: nowrap;
    position: relative; top: 2px; transition: all 0.15s;
}
.tab-item.active {
    background: #1e2128; color: #e0e0e0; font-weight: 600;
    border-color: #2a2d35;
}
.tab-item:not(.active):hover { color: #aaa; background: #16181d; }
.tab-close {
    margin-left: 0.35rem; opacity: 0.35; font-size: 0.7rem;
    cursor: pointer; padding: 0 2px; border-radius: 3px;
}
.tab-close:hover { opacity: 1; background: rgba(255,255,255,0.1); }

/* Task chips */
.task-bar { display: flex; gap: 0.5rem; overflow-x: auto; padding: 0.3rem 0; }
.task-chip {
    display: inline-flex; align-items: center; gap: 0.3rem;
    padding: 0.25rem 0.6rem; border-radius: 14px; font-size: 0.75rem;
    white-space: nowrap;
}
.chip-done    { background: #1a3a2a; color: #6fcf97; }
.chip-running { background: #2a2a1a; color: #f2c94c; }
.chip-pending { background: #1a1a2a; color: #828282; }

/* Task card compact */
.task-card-header {
    font-size: 0.85rem; font-weight: 600; margin-bottom: 0.4rem;
    color: #ccc;
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### 🗂 Workspace")

    def _render_tree(node: dict, path: list[str], depth: int = 0):
        for key, value in node.items():
            if key.startswith("_"):
                continue
            current_path = path + [key]
            path_str = "/".join(current_path)
            is_folder = isinstance(value, dict) and value.get("_type") == "folder"

            if is_folder:
                prefix = "📁" if depth > 0 else "📂"
                st.markdown(
                    f"<div style='padding:2px 0 2px {depth*12}px; "
                    f"font-size:0.82rem; color:#aaa;'>"
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
                btn_type = "primary" if is_selected else "secondary"
                if st.button(f"{icon} {key}", key=f"tree_{path_str}", use_container_width=True, type=btn_type):
                    _open_file(current_path)
                    st.rerun()

    _render_tree(st.session_state.workspace, [])

    st.divider()
    st.markdown("#### ➕ Создать")
    new_item_name = st.text_input("Имя", key="new_item_name", label_visibility="collapsed", placeholder="Новый файл.md")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("📄 Файл", use_container_width=True):
            name = st.session_state.new_item_name.strip()
            if name:
                st.session_state.workspace.setdefault("Документы", {"_type": "folder"})
                st.session_state.workspace["Документы"][name] = {"_type": "file", "content": f"# {name}\n\n"}
                _open_file(["Документы", name])
                st.rerun()
    with c2:
        if st.button("📁 Папку", use_container_width=True):
            name = st.session_state.new_item_name.strip()
            if name:
                st.session_state.workspace[name] = {"_type": "folder"}
                st.rerun()


# ---------------------------------------------------------------------------
# MAIN AREA
# ---------------------------------------------------------------------------

st.markdown(
    "<h2 style='margin:0 0 0.3rem 0; font-size:1.4rem;'>⚙️ AI Business Operating System</h2>",
    unsafe_allow_html=True,
)

col_editor, col_right = st.columns([3, 2], gap="medium")

# ---- CENTRE: Tabs + Document -------------------------------------------------
with col_editor:

    # --- Tab bar (pure HTML) ---
    if st.session_state.open_tabs:
        tabs_html = '<div class="tab-bar">'
        for idx, tab_path in enumerate(st.session_state.open_tabs):
            is_active = (
                st.session_state.selected_path is not None
                and tuple(st.session_state.selected_path) == tuple(tab_path)
            )
            cls = "tab-item active" if is_active else "tab-item"
            name = tab_path[-1]
            tabs_html += f'<span class="{cls}">{name}</span>'
        tabs_html += '</div>'
        st.markdown(tabs_html, unsafe_allow_html=True)

        # Compact button row for tab switching (hidden labels)
        num_tabs = len(st.session_state.open_tabs)
        if num_tabs > 0:
            btn_cols = st.columns(num_tabs + max(0, 6 - num_tabs))
            for idx, tab_path in enumerate(st.session_state.open_tabs):
                with btn_cols[idx]:
                    is_active = (
                        st.session_state.selected_path is not None
                        and tuple(st.session_state.selected_path) == tuple(tab_path)
                    )
                    label = tab_path[-1]
                    if is_active:
                        if st.button("✕", key=f"close_tab_{idx}", help="Закрыть вкладку"):
                            st.session_state.open_tabs.pop(idx)
                            if st.session_state.open_tabs:
                                st.session_state.selected_path = st.session_state.open_tabs[-1]
                            else:
                                st.session_state.selected_path = None
                            st.session_state.editing = False
                            st.rerun()
                    else:
                        if st.button(label, key=f"switch_tab_{idx}"):
                            st.session_state.selected_path = tab_path
                            st.session_state.editing = False
                            st.rerun()

    # --- Document view / edit ---
    if st.session_state.selected_path:
        node = _get_node(st.session_state.selected_path)
        file_name = st.session_state.selected_path[-1]

        if node and isinstance(node, dict) and node.get("_type") == "file":
            content = node.get("content", "")

            if st.session_state.editing:
                new_content = st.text_area(
                    f"Редактирование: {file_name}",
                    value=content,
                    height=400,
                    key=f"editor_{'/'.join(st.session_state.selected_path)}",
                )
                ec1, ec2, ec3 = st.columns([2, 2, 6])
                with ec1:
                    if st.button("💾 Сохранить", key="save_btn", type="primary", use_container_width=True):
                        _set_content(st.session_state.selected_path, new_content)
                        st.session_state.editing = False
                        st.rerun()
                with ec2:
                    if st.button("Отмена", key="cancel_btn", use_container_width=True):
                        st.session_state.editing = False
                        st.rerun()
            else:
                if st.button("✏️ Редактировать", key="edit_btn"):
                    st.session_state.editing = True
                    st.rerun()
                st.markdown(content)
        else:
            st.info("Выберите файл в дереве слева.")
    else:
        st.markdown("""
### 👋 Workspace OS

**Выберите файл** слева, чтобы начать работу.

- 📁 Навигация по проектам
- ✏️ Редактирование документов
- 🤖 AI-ассистент
- 📊 Отслеживание задач
        """)


# ---- RIGHT: Chat + Task card -------------------------------------------------
with col_right:
    st.markdown("#### 🤖 AI-ассистент")

    if st.session_state.selected_path:
        st.caption(f"Контекст: **{st.session_state.selected_path[-1]}**")
    else:
        st.caption("Контекст: *общий*")

    chat_container = st.container(height=300)
    with chat_container:
        if not st.session_state.chat_history:
            st.markdown(
                "<div style='color:#555; text-align:center; padding-top:2rem; font-size:0.85rem;'>"
                "Начните диалог — задайте вопрос или поставьте задачу.</div>",
                unsafe_allow_html=True,
            )
        for msg in st.session_state.chat_history:
            css_class = "chat-user" if msg["role"] == "user" else "chat-ai"
            icon = "👤" if msg["role"] == "user" else "🤖"
            st.markdown(f"<div class='{css_class}'>{icon} {msg['text']}</div>", unsafe_allow_html=True)

    user_input = st.chat_input("Задайте вопрос или поставьте задачу…")
    if user_input:
        st.session_state.chat_history.append({"role": "user", "text": user_input})
        context_note = ""
        if st.session_state.selected_path:
            node = _get_node(st.session_state.selected_path)
            if node and isinstance(node, dict):
                context_note = f"\n\n*(Контекст: {st.session_state.selected_path[-1]})*"
        ai_response = (
            f"Принято! Я обработаю запрос: «{user_input}».{context_note}\n\n"
            f"_Подключите API-ключ для полноценных ответов._"
        )
        st.session_state.chat_history.append({"role": "ai", "text": ai_response})
        st.session_state.tasks.append({
            "id": st.session_state.next_task_id,
            "title": user_input[:50] + ("…" if len(user_input) > 50 else ""),
            "status": "running",
            "ts": datetime.now().strftime("%H:%M"),
        })
        st.session_state.next_task_id += 1
        st.rerun()

    # --- Task creation card (compact, right under chat) ---
    st.markdown("---")
    st.markdown('<div class="task-card-header">➕ Новая задача</div>', unsafe_allow_html=True)

    task_type = st.radio(
        "Тип", ["🔌 MCP", "🤖 LLM", "💻 Code"],
        horizontal=True, key="task_type_radio", label_visibility="collapsed",
    )

    task_prompt = st.text_input("Промт", key="task_prompt", placeholder="Опишите задачу…", label_visibility="collapsed")

    tf1, tf2 = st.columns(2)
    with tf1:
        all_files = _collect_files(st.session_state.workspace, [])
        file_options = ["— нет —"] + ["/".join(fp) for fp in all_files]
        selected_file = st.selectbox("📄 Файл", options=file_options, key="task_file", label_visibility="collapsed")
    with tf2:
        if task_type == "🔌 MCP":
            tool_opts = ["file_read", "file_write", "web_search", "code_execute", "database_query", "api_call"]
            selected_tool = st.selectbox("🔧 Инструмент", options=tool_opts, key="task_tool", label_visibility="collapsed")
        elif task_type == "🤖 LLM":
            llm_opts = ["Claude Opus", "Claude Sonnet", "Claude Haiku", "GPT-4o", "Gemini Pro"]
            selected_tool = st.selectbox("🧠 Модель", options=llm_opts, key="task_llm", label_visibility="collapsed")
        else:
            lang_opts = ["Python", "JavaScript", "TypeScript", "Bash", "SQL"]
            selected_tool = st.selectbox("💻 Язык", options=lang_opts, key="task_lang", label_visibility="collapsed")

    if st.button("🚀 Запустить", key="run_task_btn", type="primary", use_container_width=True):
        if task_prompt.strip():
            type_map = {"🔌 MCP": "MCP", "🤖 LLM": "LLM", "💻 Code": "Code"}
            title = f"[{type_map.get(task_type, '?')}] {task_prompt.strip()[:40]}"
            st.session_state.tasks.append({
                "id": st.session_state.next_task_id,
                "title": title,
                "status": "running",
                "ts": datetime.now().strftime("%H:%M"),
                "type": task_type,
                "prompt": task_prompt.strip(),
                "file": selected_file if selected_file != "— нет —" else None,
                "tool": selected_tool,
            })
            st.session_state.next_task_id += 1
            st.rerun()
        else:
            st.warning("Введите описание задачи.")


# ---------------------------------------------------------------------------
# BOTTOM BAR — task pipeline
# ---------------------------------------------------------------------------

st.divider()

status_icons = {"done": "✅", "running": "⏳", "pending": "⏸️"}
status_classes = {"done": "chip-done", "running": "chip-running", "pending": "chip-pending"}

chips_html = '<div class="task-bar">'
for task in st.session_state.tasks:
    icon = status_icons.get(task["status"], "❓")
    cls = status_classes.get(task["status"], "chip-pending")
    chips_html += (
        f'<span class="task-chip {cls}">{icon} {task["title"]} '
        f'<span style="opacity:0.5;">({task["ts"]})</span></span>'
    )
chips_html += '</div>'
st.markdown(chips_html, unsafe_allow_html=True)

with st.expander("🔧 Управление задачами"):
    if st.session_state.tasks:
        for i, task in enumerate(st.session_state.tasks):
            tc1, tc2, tc3 = st.columns([5, 1, 1])
            with tc1:
                icon = status_icons.get(task["status"], "❓")
                st.markdown(f"{icon} **{task['title']}** `{task['ts']}`")
            with tc2:
                new_status = st.selectbox(
                    "s", ["pending", "running", "done"],
                    index=["pending", "running", "done"].index(task["status"]),
                    key=f"task_status_{task['id']}", label_visibility="collapsed",
                )
                if new_status != task["status"]:
                    st.session_state.tasks[i]["status"] = new_status
                    st.rerun()
            with tc3:
                if st.button("🗑", key=f"del_task_{task['id']}"):
                    st.session_state.tasks.pop(i)
                    st.rerun()
