import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.config import settings


@pytest.mark.asyncio
async def test_url_verification():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/webhook/feishu", json={
            "type": "url_verification",
            "token": settings.FEISHU_VERIFICATION_TOKEN,
            "challenge": "test-challenge-123",
        })
    assert resp.status_code == 200
    assert resp.json()["challenge"] == "test-challenge-123"


@pytest.mark.asyncio
async def test_duplicate_event_ignored():
    """同一 event_id 第二次请求应被忽略（幂等）。"""
    from app.feishu.webhook import _processed_ids
    _processed_ids.clear()

    payload = {
        "schema": "2.0",
        "header": {"event_id": "dup-001", "event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_test"}},
            "message": {
                "message_id": "msg-001",
                "chat_id": "oc_test",
                "chat_type": "p2p",
                "message_type": "text",
                "content": '{"text":"星巴克35"}',
            },
        },
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.post("/webhook/feishu", json=payload)
        r2 = await client.post("/webhook/feishu", json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 200
    # 队列里只有一条
    from app.feishu.webhook import message_queue
    assert message_queue.qsize() == 1
    # 清空
    while not message_queue.empty():
        message_queue.get_nowait()


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
