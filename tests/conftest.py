"""Shared fixtures and helpers for all tests."""

import json
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.models import (
    AsIsModel,
    AutomationOpportunity,
    Base,
    Company,
    Gap,
    InterviewSession,
    Process,
    PublishedPage,
    RawInput,
    Respondent,
)
from bot.states import (
    GapFieldType,
    GapStatus,
    OpportunityStatus,
    OpportunityType,
    ProcessStatus,
    SessionStatus,
)


# ---------------------------------------------------------------------------
# Async event-loop
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# In-memory database
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture()
async def db_session(db_engine):
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest.fixture()
def patch_db(db_engine):
    """Patch bot.database.async_session everywhere it's imported."""
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    targets = [
        "bot.database.async_session",
        "bot.handlers.start.async_session",
        "bot.handlers.interview.async_session",
        "bot.handlers.clarification.async_session",
        "bot.handlers.opportunities.async_session",
        "bot.handlers.callbacks.async_session",
    ]
    patches = [patch(t, session_factory) for t in targets]
    for p in patches:
        p.start()
    yield session_factory
    for p in patches:
        p.stop()


# ---------------------------------------------------------------------------
# Seed data helpers
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def seed_company(db_session):
    c = Company(name="TestCo")
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


@pytest_asyncio.fixture()
async def seed_respondent(db_session):
    r = Respondent(telegram_user_id=111222, display_name="Иван Тест")
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    return r


@pytest_asyncio.fixture()
async def seed_process(db_session, seed_company):
    p = Process(
        company_id=seed_company.id,
        name="Онбординг",
        status=ProcessStatus.CREATED,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest_asyncio.fixture()
async def seed_session(db_session, seed_process, seed_respondent):
    s = InterviewSession(
        process_id=seed_process.id,
        respondent_id=seed_respondent.id,
        state=SessionStatus.STARTED,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


@pytest_asyncio.fixture()
async def seed_asis_model(db_session, seed_process):
    m = AsIsModel(
        process_id=seed_process.id,
        goal="Ввести нового сотрудника",
        summary="Процесс онбординга",
        stages=json.dumps([
            {
                "id": "stage_1",
                "name": "Оформление документов",
                "description": "HR оформляет документы",
                "owner_role": "HR",
                "systems": ["1С"],
                "inputs": ["Паспорт"],
                "outputs": ["Трудовой договор"],
                "artifacts": ["Договор"],
                "metrics": [],
                "sla": "1 день",
                "pain_points": ["Ручной ввод данных"],
                "handoff_to": "stage_2",
            },
            {
                "id": "stage_2",
                "name": "Настройка рабочего места",
                "description": "IT настраивает оборудование",
                "owner_role": "IT",
                "systems": ["Jira"],
                "inputs": ["Заявка"],
                "outputs": ["Готовое рабочее место"],
                "artifacts": [],
                "metrics": [],
                "sla": "2 дня",
                "pain_points": [],
                "handoff_to": None,
            },
        ], ensure_ascii=False),
        roles=json.dumps(["HR", "IT"], ensure_ascii=False),
        systems=json.dumps(["1С", "Jira"], ensure_ascii=False),
        triggers=json.dumps(["Подписан оффер"], ensure_ascii=False),
        inputs=json.dumps(["Паспорт", "Оффер"], ensure_ascii=False),
        outputs=json.dumps(["Готовое рабочее место"], ensure_ascii=False),
        artifacts=json.dumps(["Трудовой договор"], ensure_ascii=False),
        metrics=json.dumps([], ensure_ascii=False),
        pain_points=json.dumps(["Ручной ввод данных"], ensure_ascii=False),
        handoffs=json.dumps(["HR → IT"], ensure_ascii=False),
        completeness_score=0.7,
    )
    db_session.add(m)
    await db_session.commit()
    await db_session.refresh(m)
    return m


@pytest_asyncio.fixture()
async def seed_gaps(db_session, seed_process):
    gaps = []
    for i, (ft, q) in enumerate([
        (GapFieldType.METRICS, "Какие метрики отслеживаются на этапе 'Оформление'?"),
        (GapFieldType.SYSTEMS, "В какой системе создается заявка на настройку рабочего места?"),
        (GapFieldType.ARTIFACTS, "Какой документ подтверждает завершение онбординга?"),
    ]):
        g = Gap(
            process_id=seed_process.id,
            stage_id=f"stage_{i + 1}" if i < 2 else None,
            field_type=ft,
            question_text=q,
            confidence_score=0.3 + i * 0.1,
            status=GapStatus.PENDING,
        )
        db_session.add(g)
        gaps.append(g)

    await db_session.commit()
    for g in gaps:
        await db_session.refresh(g)
    return gaps


@pytest_asyncio.fixture()
async def seed_opportunities(db_session, seed_process):
    opps = []
    for title, problem, benefit, otype in [
        (
            "Автопарсинг документов",
            "HR вручную вносит данные из паспорта",
            "Сокращение ошибок на 80%",
            OpportunityType.AI,
        ),
        (
            "Авто-создание заявок в Jira",
            "IT получает заявку по email",
            "Сокращение времени на 50%",
            OpportunityType.INTEGRATION,
        ),
        (
            "Дашборд онбординга",
            "Нет видимости статуса",
            "Прозрачность процесса",
            OpportunityType.ANALYTICS,
        ),
    ]:
        o = AutomationOpportunity(
            process_id=seed_process.id,
            title=title,
            opp_type=otype,
            problem=problem,
            expected_benefit=benefit,
            status=OpportunityStatus.PROPOSED,
        )
        db_session.add(o)
        opps.append(o)

    await db_session.commit()
    for o in opps:
        await db_session.refresh(o)
    return opps


# ---------------------------------------------------------------------------
# Telegram mock helpers
# ---------------------------------------------------------------------------

class BotMock:
    """A mock bot that doesn't auto-create attributes like MagicMock does."""

    def __init__(self):
        self.send_message = AsyncMock()
        self.get_file = AsyncMock()


def make_bot_mock():
    """Create a properly mocked bot with all async methods."""
    return BotMock()


def make_update(
    text: str = "",
    chat_id: int = 99999,
    user_id: int = 111222,
    user_name: str = "Иван Тест",
    message_id: int = 1,
    args: list[str] | None = None,
    voice: MagicMock | None = None,
    audio: MagicMock | None = None,
    document: MagicMock | None = None,
):
    """Create a mock telegram.Update for testing."""
    bot = make_bot_mock()

    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.full_name = user_name
    update.effective_chat = MagicMock()
    update.effective_chat.id = chat_id
    update.message = MagicMock()
    update.message.text = text
    update.message.message_id = message_id
    update.message.reply_text = AsyncMock()
    update.message.voice = voice
    update.message.audio = audio
    update.message.document = document
    update.get_bot = MagicMock(return_value=bot)

    context = MagicMock()
    context.args = args or []
    context.bot = bot
    return update, context


def make_callback_query(data: str, chat_id: int = 99999):
    """Create a mock callback query update."""
    bot = make_bot_mock()

    update = MagicMock()
    update.callback_query = MagicMock()
    update.callback_query.data = data
    update.callback_query.answer = AsyncMock()
    update.callback_query.message = MagicMock()
    update.callback_query.message.chat_id = chat_id
    update.effective_chat = MagicMock()
    update.effective_chat.id = chat_id

    context = MagicMock()
    context.bot = bot
    return update, context


# ---------------------------------------------------------------------------
# Sample LLM responses
# ---------------------------------------------------------------------------

SAMPLE_ASIS_MODEL = {
    "goal": "Ввести нового сотрудника",
    "summary": "Процесс онбординга нового сотрудника",
    "triggers": ["Подписан оффер"],
    "inputs": ["Паспорт", "Оффер"],
    "outputs": ["Готовое рабочее место"],
    "stages": [
        {
            "id": "stage_1",
            "name": "Оформление документов",
            "description": "HR оформляет документы",
            "owner_role": "HR",
            "systems": ["1С"],
            "inputs": ["Паспорт"],
            "outputs": ["Трудовой договор"],
            "artifacts": ["Договор"],
            "metrics": [],
            "sla": "1 день",
            "pain_points": ["Ручной ввод"],
            "handoff_to": "stage_2",
        }
    ],
    "roles": ["HR", "IT"],
    "systems": ["1С", "Jira"],
    "artifacts": ["Трудовой договор"],
    "metrics": [],
    "pain_points": ["Ручной ввод данных"],
    "handoffs": ["HR → IT"],
}

SAMPLE_GAP_RESULT = {
    "completeness_score": 0.55,
    "gaps": [
        {
            "stage_id": "stage_1",
            "field_type": "metrics",
            "question": "Какие метрики отслеживаются на этапе 'Оформление'?",
            "confidence": 0.3,
        },
        {
            "stage_id": None,
            "field_type": "systems",
            "question": "Какие ещё системы используются в процессе?",
            "confidence": 0.4,
        },
    ],
}

SAMPLE_GAP_RESULT_HIGH = {
    "completeness_score": 0.85,
    "gaps": [],
}

SAMPLE_NARRATIVE = {
    "title": "Онбординг",
    "goal": "Ввести нового сотрудника в компанию",
    "summary": "Процесс состоит из двух основных этапов.",
    "triggers_html": "<ul><li>Подписан оффер</li></ul>",
    "inputs_html": "<ul><li>Паспорт</li><li>Оффер</li></ul>",
    "outputs_html": "<ul><li>Готовое рабочее место</li></ul>",
    "roles_html": "<ul><li>HR</li><li>IT</li></ul>",
    "systems_html": "<ul><li>1С</li><li>Jira</li></ul>",
    "artifacts_html": "<ul><li>Трудовой договор</li></ul>",
    "stages_html": "<h3>1. Оформление документов</h3><p>HR оформляет.</p>",
    "metrics_html": "",
    "pain_points_html": "<ul><li>Ручной ввод данных</li></ul>",
    "automation_candidates_html": "<ul><li>Автопарсинг</li></ul>",
}

SAMPLE_MERMAID = """flowchart TD
    A[Подписан оффер] --> B[Оформление документов]
    B --> C[Настройка рабочего места]
    C --> D[Готово]"""

SAMPLE_OPPORTUNITIES = [
    {
        "title": "Автопарсинг документов",
        "stage_id": "stage_1",
        "type": "ai",
        "problem": "HR вручную вносит данные",
        "description": "OCR + AI извлечение данных из документов",
        "expected_benefit": "Сокращение ошибок на 80%",
    },
    {
        "title": "Авто-создание заявок",
        "stage_id": "stage_2",
        "type": "integration",
        "problem": "Заявки создаются вручную",
        "description": "Автоматическое создание заявки в Jira",
        "expected_benefit": "Экономия 30 мин",
    },
]
