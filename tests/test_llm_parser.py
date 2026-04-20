import json
from datetime import date
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.llm.parser import parse_expense


def _mock_response(data: dict):
    choice = MagicMock()
    choice.message.content = json.dumps(data, ensure_ascii=False)
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_parse_standard_expense():
    mock = AsyncMock(return_value=_mock_response({
        "amount": 35, "category": "餐饮", "note": "星巴克", "date": "2026-04-20"
    }))
    with patch("app.llm.parser.get_llm_client") as m:
        m.return_value.chat.completions.create = mock
        result = await parse_expense("星巴克35")

    assert result is not None
    assert result.amount == 35.0
    assert result.category == "餐饮"
    assert result.note == "星巴克"


@pytest.mark.asyncio
async def test_parse_income():
    mock = AsyncMock(return_value=_mock_response({
        "amount": -15000, "category": "收入", "note": "工资", "date": "2026-04-20"
    }))
    with patch("app.llm.parser.get_llm_client") as m:
        m.return_value.chat.completions.create = mock
        result = await parse_expense("收到工资15000")

    assert result is not None
    assert result.amount == -15000.0
    assert result.category == "收入"


@pytest.mark.asyncio
async def test_parse_no_amount():
    mock = AsyncMock(return_value=_mock_response({"error": "no_amount"}))
    with patch("app.llm.parser.get_llm_client") as m:
        m.return_value.chat.completions.create = mock
        result = await parse_expense("今天心情不好")

    assert result is None


@pytest.mark.asyncio
async def test_parse_with_date():
    mock = AsyncMock(return_value=_mock_response({
        "amount": 12, "category": "交通", "note": "地铁", "date": "2026-04-19"
    }))
    with patch("app.llm.parser.get_llm_client") as m:
        m.return_value.chat.completions.create = mock
        result = await parse_expense("昨天地铁12")

    assert result is not None
    assert result.date == date(2026, 4, 19)
