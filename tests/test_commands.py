import pytest
from datetime import date
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.database import Base
from app.commands.query import get_or_create_user, add_transaction, query_month_summary, query_recent
from app.commands.router import handle_message


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_or_create_user_new(session):
    user = await get_or_create_user(session, "ou_new")
    assert user.id is not None


@pytest.mark.asyncio
async def test_get_or_create_user_idempotent(session):
    u1 = await get_or_create_user(session, "ou_same")
    u2 = await get_or_create_user(session, "ou_same")
    assert u1.id == u2.id


@pytest.mark.asyncio
async def test_add_and_query_month(session):
    user = await get_or_create_user(session, "ou_test")
    await add_transaction(session, user.id, 35.0, "餐饮", "星巴克", date(2026, 4, 20))
    await add_transaction(session, user.id, 12.0, "交通", "地铁", date(2026, 4, 19))

    summary = await query_month_summary(session, user.id, 2026, 4)
    assert "¥47.00" in summary or "餐饮" in summary


@pytest.mark.asyncio
async def test_query_empty_month(session):
    user = await get_or_create_user(session, "ou_empty")
    summary = await query_month_summary(session, user.id, 2020, 1)
    assert "暂无记录" in summary


@pytest.mark.asyncio
async def test_handle_help(session):
    reply = await handle_message(session, "ou_test", "/帮助")
    assert "记账" in reply


@pytest.mark.asyncio
async def test_handle_record_via_router(session):
    mock_parsed = AsyncMock(return_value=type("P", (), {
        "amount": 35.0, "category": "餐饮", "note": "星巴克", "date": date(2026, 4, 20)
    })())
    with patch("app.commands.router.parse_expense", mock_parsed):
        reply = await handle_message(session, "ou_router", "星巴克35")
    assert "已记录" in reply or "餐饮" in reply


@pytest.mark.asyncio
async def test_handle_no_amount(session):
    mock_parsed = AsyncMock(return_value=None)
    with patch("app.commands.router.parse_expense", mock_parsed):
        reply = await handle_message(session, "ou_noamt", "今天心情不好")
    assert "没识别到金额" in reply
