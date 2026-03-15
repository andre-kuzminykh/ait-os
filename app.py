"""
AI Business Operating System (AI BOS) — Workspace OS
Единая среда работы человека и ИИ на Streamlit.
"""

from __future__ import annotations

import streamlit as st
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
# Session state defaults
# ---------------------------------------------------------------------------

DEFAULT_WORKSPACE: dict = {
    "Проекты": {
        "_type": "folder",
        "_open": True,
        "AI BOS": {
            "_type": "folder",
            "_open": True,
            "PRD.md": {"_type": "file", "content": "# PRD — AI Business Operating System\n\nОписание продукта…"},
            "Архитектура.md": {"_type": "file", "content": "# Архитектура\n\n## Компоненты\n- Frontend (Streamlit)\n- Backend API\n- LLM Service"},
            "Бэклог.md": {"_type": "file", "content": "# Бэклог\n\n- [ ] MVP интерфейса\n- [ ] Интеграция с LLM\n- [ ] Система задач"},
        },
        "Маркетинг": {
            "_type": "folder",
            "_open": False,
            "Стратегия.md": {"_type": "file", "content": "# Маркетинговая стратегия\n\n## Каналы\n1. SEO\n2. Content marketing\n3. Community"},
        },
    },
    "Документы": {
        "_type": "folder",
        "_open": False,
        "Заметки.md": {"_type": "file", "content": "# Заметки\n\nРабочие заметки и идеи…"},
        "Шаблон отчёта.md": {"_type": "file", "content": "# Отчёт\n\n## Период: …\n## Результаты\n…"},
    },
    "Данные": {
        "_type": "folder",
        "_open": False,
        "KPI Q1.md": {"_type": "file", "content": "# KPI Q1 2026\n\n| Метрика | План | Факт |\n|---------|------|------|\n| Revenue | 100k | 95k  |\n| Users   | 10k  | 12k  |"},
    },
}

if "workspace" not in st.session_state:
    st.session_state.workspace = DEFAULT_WORKSPACE
if "view" not in st.session_state:
    st.session_state.view = "home"  # "home" or "file"
if "selected_path" not in st.session_state:
    st.session_state.selected_path = None
if "open_tabs" not in st.session_state:
    st.session_state.open_tabs = []
if "editing" not in st.session_state:
    st.session_state.editing = False
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "tasks" not in st.session_state:
    st.session_state.tasks = [
        {"id": 1, "title": "Сгенерировать PRD", "status": "done", "ts": "14:02", "type": "LLM"},
        {"id": 2, "title": "Проанализировать KPI", "status": "running", "ts": "14:15", "type": "LLM"},
        {"id": 3, "title": "Подготовить отчёт", "status": "pending", "ts": "—", "type": "MCP"},
    ]
if "next_task_id" not in st.session_state:
    st.session_state.next_task_id = 4
# Track which folder is being created in (path as "/"-joined string, or None)
if "creating_in" not in st.session_state:
    st.session_state.creating_in = None

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


def _set_node_key(path: list[str], key: str, value):
    """Set a key on the node at path."""
    node = st.session_state.workspace
    for part in path:
        node = node[part]
    node[key] = value


def _set_content(path: list[str], content: str):
    node = st.session_state.workspace
    for part in path[:-1]:
        node = node[part]
    node[path[-1]]["content"] = content


def _add_item(parent_path: list[str], name: str, item: dict):
    """Add a file or folder to the workspace tree."""
    node = st.session_state.workspace
    for part in parent_path:
        node = node[part]
    node[name] = item


def _open_file(path: list[str]):
    st.session_state.selected_path = path
    st.session_state.view = "file"
    st.session_state.editing = False
    if tuple(path) not in [tuple(t) for t in st.session_state.open_tabs]:
        st.session_state.open_tabs.append(path)


def _go_home():
    st.session_state.view = "home"
    st.session_state.selected_path = None
    st.session_state.editing = False


def _create_task(title: str, task_type: str = "LLM"):
    """Create a new running task."""
    st.session_state.tasks.append({
        "id": st.session_state.next_task_id,
        "title": title,
        "status": "running",
        "ts": datetime.now().strftime("%H:%M"),
        "type": task_type,
    })
    st.session_state.next_task_id += 1


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

st.markdown("""
<style>
/* Global */
.block-container { padding-top: 0.7rem !important; padding-bottom: 0 !important; }
h2 { font-size: 1.3rem !important; margin: 0 0 0.3rem 0 !important; }

/* ---- Sidebar ---- */
div[data-testid="stSidebar"] {
    padding-top: 0.5rem;
}
div[data-testid="stSidebar"] .stButton > button {
    text-align: left !important;
    padding: 0.12rem 0.4rem !important;
    font-size: 0.82rem !important;
    background: transparent !important;
    border: none !important;
    color: #bbb !important;
    width: 100% !important;
    border-radius: 3px !important;
    transition: background 0.1s;
}
div[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.06) !important;
    color: #fff !important;
}
div[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: rgba(79,139,249,0.18) !important;
    color: #7ab3ff !important;
    font-weight: 600 !important;
}

/* Folder row */
.folder-row {
    display: flex; align-items: center; gap: 0.3rem;
    padding: 2px 0; font-size: 0.82rem; color: #aaa;
    cursor: default; user-select: none;
}
.folder-row:hover { color: #ddd; }
.folder-toggle { font-size: 0.65rem; color: #666; width: 12px; display: inline-block; text-align: center; }

/* ---- Chat ---- */
.chat-user {
    background: #1e2a3a; border-radius: 8px;
    padding: 0.45rem 0.65rem; margin: 0.2rem 0; font-size: 0.85rem;
}
.chat-ai {
    background: #1a2520; border-radius: 8px;
    padding: 0.45rem 0.65rem; margin: 0.2rem 0; font-size: 0.85rem;
}

/* ---- Tab bar ---- */
.tab-bar {
    display: flex; gap: 0; border-bottom: 2px solid #2a2d35;
    margin-bottom: 0.5rem; overflow-x: auto; scrollbar-width: thin;
}
.tab-item {
    padding: 0.35rem 0.85rem; font-size: 0.78rem;
    border: 1px solid transparent; border-bottom: none;
    border-radius: 5px 5px 0 0; color: #666;
    white-space: nowrap; position: relative; top: 2px;
}
.tab-item.active {
    background: #1e2128; color: #e0e0e0; font-weight: 600;
    border-color: #2a2d35;
}

/* ---- Task cards on home ---- */
.task-card {
    background: #16181e; border: 1px solid #252830; border-radius: 8px;
    padding: 0.7rem 0.9rem; margin-bottom: 0.5rem;
    display: flex; align-items: center; justify-content: space-between;
}
.task-card-left { display: flex; align-items: center; gap: 0.5rem; }
.task-title { font-size: 0.88rem; color: #ddd; }
.task-meta { font-size: 0.72rem; color: #666; }
.badge {
    padding: 0.15rem 0.5rem; border-radius: 10px; font-size: 0.7rem;
    font-weight: 600; display: inline-block;
}
.badge-done    { background: #1a3a2a; color: #6fcf97; }
.badge-running { background: #2a2a1a; color: #f2c94c; }
.badge-pending { background: #1e1e2e; color: #828282; }
.badge-type    { background: #1a2030; color: #7ab3ff; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# SIDEBAR — File Explorer (Windows-style)
# ---------------------------------------------------------------------------

with st.sidebar:
    # Home button
    if st.button("🏠 Главная", key="nav_home", use_container_width=True):
        _go_home()
        st.rerun()

    st.markdown(
        "<div style='font-size:0.75rem; color:#555; text-transform:uppercase; "
        "letter-spacing:0.08em; padding:0.5rem 0 0.2rem 0.3rem;'>Проводник</div>",
        unsafe_allow_html=True,
    )

    def _render_tree(node: dict, path: list[str], depth: int = 0):
        for key, value in sorted(node.items()):
            if key.startswith("_"):
                continue
            current_path = path + [key]
            path_str = "/".join(current_path)
            is_folder = isinstance(value, dict) and value.get("_type") == "folder"

            if is_folder:
                is_open = value.get("_open", False)
                arrow = "▼" if is_open else "▶"
                indent = depth * 16

                # Folder toggle button
                if st.button(
                    f"{arrow}  📁 {key}",
                    key=f"folder_{path_str}",
                    use_container_width=True,
                ):
                    _set_node_key(current_path, "_open", not is_open)
                    st.rerun()

                # Show children if open
                if is_open:
                    _render_tree(value, current_path, depth + 1)

                    # Inline "+" button to create inside this folder
                    create_key = path_str
                    if st.session_state.creating_in == create_key:
                        new_name = st.text_input(
                            "Имя",
                            key=f"new_name_{create_key}",
                            placeholder="имя_файла.md",
                            label_visibility="collapsed",
                        )
                        cc1, cc2, cc3 = st.columns([2, 2, 1])
                        with cc1:
                            if st.button("📄", key=f"mk_file_{create_key}", help="Создать файл"):
                                if new_name.strip():
                                    _add_item(current_path, new_name.strip(), {
                                        "_type": "file",
                                        "content": f"# {new_name.strip()}\n\n",
                                    })
                                    _open_file(current_path + [new_name.strip()])
                                    _create_task(f"Создание: {new_name.strip()}", "Code")
                                    st.session_state.creating_in = None
                                    st.rerun()
                        with cc2:
                            if st.button("📁", key=f"mk_folder_{create_key}", help="Создать папку"):
                                if new_name.strip():
                                    _add_item(current_path, new_name.strip(), {
                                        "_type": "folder", "_open": True,
                                    })
                                    st.session_state.creating_in = None
                                    st.rerun()
                        with cc3:
                            if st.button("✕", key=f"cancel_mk_{create_key}"):
                                st.session_state.creating_in = None
                                st.rerun()
                    else:
                        if st.button(
                            f"＋ Создать…",
                            key=f"add_in_{create_key}",
                            use_container_width=True,
                        ):
                            st.session_state.creating_in = create_key
                            st.rerun()

            else:
                # File button
                is_selected = (
                    st.session_state.selected_path is not None
                    and "/".join(st.session_state.selected_path) == path_str
                )
                icon = "📝" if key.endswith(".md") else "📄"
                btn_type = "primary" if is_selected else "secondary"
                if st.button(
                    f"{'  ' * depth}{icon} {key}",
                    key=f"file_{path_str}",
                    use_container_width=True,
                    type=btn_type,
                ):
                    _open_file(current_path)
                    st.rerun()

    _render_tree(st.session_state.workspace, [])


# ---------------------------------------------------------------------------
# MAIN AREA
# ---------------------------------------------------------------------------

st.markdown("## ⚙️ AI Business Operating System")

col_center, col_chat = st.columns([3, 2], gap="medium")

# ---- CENTER: Home dashboard OR File editor ------------------------------------
with col_center:

    if st.session_state.view == "home":
        # ===== HOME — Task dashboard =====
        st.markdown("### 📋 Задачи")

        status_filter = st.radio(
            "Фильтр",
            ["Все", "В работе", "Готово", "Ожидание"],
            horizontal=True,
            label_visibility="collapsed",
        )
        filter_map = {"Все": None, "В работе": "running", "Готово": "done", "Ожидание": "pending"}
        active_filter = filter_map[status_filter]

        filtered = [t for t in st.session_state.tasks if active_filter is None or t["status"] == active_filter]

        if not filtered:
            st.info("Нет задач в этой категории.")
        else:
            for task in filtered:
                status = task["status"]
                icon = {"done": "✅", "running": "⏳", "pending": "⏸️"}.get(status, "❓")
                badge_cls = f"badge-{status}"
                status_label = {"done": "Готово", "running": "В работе", "pending": "Ожидание"}.get(status, "?")
                task_type = task.get("type", "")

                st.markdown(
                    f'<div class="task-card">'
                    f'  <div class="task-card-left">'
                    f'    <span style="font-size:1.2rem;">{icon}</span>'
                    f'    <div>'
                    f'      <div class="task-title">{task["title"]}</div>'
                    f'      <div class="task-meta">{task["ts"]}'
                    f'        {f" · <span class=badge badge-type>{task_type}</span>" if task_type else ""}'
                    f'      </div>'
                    f'    </div>'
                    f'  </div>'
                    f'  <span class="badge {badge_cls}">{status_label}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # Task management (status change / delete)
        with st.expander("🔧 Управление задачами"):
            if st.session_state.tasks:
                for i, task in enumerate(st.session_state.tasks):
                    tc1, tc2, tc3 = st.columns([5, 2, 1])
                    with tc1:
                        st.markdown(f"**{task['title']}**")
                    with tc2:
                        new_status = st.selectbox(
                            "s",
                            ["pending", "running", "done"],
                            index=["pending", "running", "done"].index(task["status"]),
                            key=f"ts_{task['id']}",
                            label_visibility="collapsed",
                        )
                        if new_status != task["status"]:
                            st.session_state.tasks[i]["status"] = new_status
                            st.rerun()
                    with tc3:
                        if st.button("🗑", key=f"del_{task['id']}"):
                            st.session_state.tasks.pop(i)
                            st.rerun()

    else:
        # ===== FILE VIEW — Tabs + Editor =====

        # Tab bar (HTML display)
        if st.session_state.open_tabs:
            tabs_html = '<div class="tab-bar">'
            for idx, tab_path in enumerate(st.session_state.open_tabs):
                is_active = (
                    st.session_state.selected_path is not None
                    and tuple(st.session_state.selected_path) == tuple(tab_path)
                )
                cls = "tab-item active" if is_active else "tab-item"
                tabs_html += f'<span class="{cls}">{tab_path[-1]}</span>'
            tabs_html += '</div>'
            st.markdown(tabs_html, unsafe_allow_html=True)

            # Interactive tab buttons (compact)
            num_tabs = len(st.session_state.open_tabs)
            tab_cols = st.columns(min(num_tabs, 8))
            for idx, tab_path in enumerate(st.session_state.open_tabs):
                if idx >= 8:
                    break
                with tab_cols[idx]:
                    is_active = (
                        st.session_state.selected_path is not None
                        and tuple(st.session_state.selected_path) == tuple(tab_path)
                    )
                    if is_active:
                        if st.button("✕ Закрыть", key=f"close_{idx}", use_container_width=True):
                            st.session_state.open_tabs.pop(idx)
                            if st.session_state.open_tabs:
                                st.session_state.selected_path = st.session_state.open_tabs[-1]
                            else:
                                _go_home()
                            st.rerun()
                    else:
                        if st.button(tab_path[-1], key=f"sw_{idx}", use_container_width=True):
                            st.session_state.selected_path = tab_path
                            st.session_state.editing = False
                            st.rerun()

        # Document content
        if st.session_state.selected_path:
            node = _get_node(st.session_state.selected_path)
            fname = st.session_state.selected_path[-1]

            if node and isinstance(node, dict) and node.get("_type") == "file":
                content = node.get("content", "")

                if st.session_state.editing:
                    new_content = st.text_area(
                        f"Редактирование: {fname}",
                        value=content,
                        height=420,
                        key=f"ed_{'/'.join(st.session_state.selected_path)}",
                    )
                    c1, c2, _ = st.columns([1, 1, 4])
                    with c1:
                        if st.button("💾 Сохранить", type="primary", use_container_width=True):
                            _set_content(st.session_state.selected_path, new_content)
                            st.session_state.editing = False
                            st.rerun()
                    with c2:
                        if st.button("Отмена", use_container_width=True):
                            st.session_state.editing = False
                            st.rerun()
                else:
                    # Header: filename + path + edit button
                    h1, h2 = st.columns([4, 1])
                    with h1:
                        breadcrumb = " / ".join(st.session_state.selected_path[:-1])
                        st.caption(f"📁 {breadcrumb}")
                        st.markdown(f"**{fname}**")
                    with h2:
                        if st.button("✏️ Редактировать", use_container_width=True):
                            st.session_state.editing = True
                            st.rerun()

                    st.markdown("---")
                    st.markdown(content)
            else:
                st.info("Файл не найден.")
        else:
            _go_home()
            st.rerun()


# ---- RIGHT: AI Chat -----------------------------------------------------------
with col_chat:
    st.markdown("#### 🤖 AI-ассистент")

    if st.session_state.selected_path:
        st.caption(f"Контекст: **{st.session_state.selected_path[-1]}**")
    else:
        st.caption("Контекст: *общий*")

    chat_box = st.container(height=400)
    with chat_box:
        if not st.session_state.chat_history:
            st.markdown(
                "<div style='color:#555; text-align:center; padding-top:3rem; "
                "font-size:0.85rem;'>Начните диалог — задайте вопрос или поставьте задачу.</div>",
                unsafe_allow_html=True,
            )
        for msg in st.session_state.chat_history:
            css = "chat-user" if msg["role"] == "user" else "chat-ai"
            icon = "👤" if msg["role"] == "user" else "🤖"
            st.markdown(f"<div class='{css}'>{icon} {msg['text']}</div>", unsafe_allow_html=True)

    user_input = st.chat_input("Задайте вопрос или поставьте задачу…")
    if user_input:
        st.session_state.chat_history.append({"role": "user", "text": user_input})

        ctx = ""
        if st.session_state.selected_path:
            ctx = f"\n\n*(Контекст: {st.session_state.selected_path[-1]})*"

        ai_resp = f"Принято! Обработаю запрос: «{user_input}».{ctx}\n\n_Подключите API для реальных ответов._"
        st.session_state.chat_history.append({"role": "ai", "text": ai_resp})

        _create_task(user_input[:50] + ("…" if len(user_input) > 50 else ""), "LLM")
        st.rerun()
