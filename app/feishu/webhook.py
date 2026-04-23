import asyncio
import json
import logging
from collections import deque
from dataclasses import dataclass

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# 已处理的消息 ID，防止飞书重试导致重复处理（内存级别，重启后清空）
_MAX_DEDUP = 10000
_processed_ids: set[str] = set()
_processed_order: deque[str] = deque()

# 消息队列：Webhook 立即入队返回，后台消费处理
message_queue: asyncio.Queue = asyncio.Queue()


@dataclass
class FeishuMessage:
    message_id: str
    open_id: str
    chat_id: str
    text: str


@router.post("/webhook/feishu")
async def feishu_webhook(request: Request) -> JSONResponse:
    body = await request.json()

    # URL 验证（飞书配置 Webhook 时的握手请求）
    if body.get("type") == "url_verification":
        token = body.get("token", "")
        if token != settings.FEISHU_VERIFICATION_TOKEN:
            return JSONResponse({"error": "invalid token"}, status_code=403)
        return JSONResponse({"challenge": body["challenge"]})

    # 普通事件
    header = body.get("header", {})
    event_type = header.get("event_type", "")
    event_id = header.get("event_id", "")

    # 幂等：同一 event_id 只处理一次
    if event_id in _processed_ids:
        return JSONResponse({"code": 0})
    _processed_ids.add(event_id)
    _processed_order.append(event_id)
    # 超过上限时移除最旧的记录，避免内存无限增长
    if len(_processed_order) > _MAX_DEDUP:
        oldest = _processed_order.popleft()
        _processed_ids.discard(oldest)

    if event_type == "im.message.receive_v1":
        event = body.get("event", {})
        msg = event.get("message", {})
        sender = event.get("sender", {})

        if msg.get("message_type") != "text":
            return JSONResponse({"code": 0})

        message_id = msg.get("message_id", "")
        open_id = sender.get("sender_id", {}).get("open_id", "")
        chat_id = msg.get("chat_id", "")
        content = json.loads(msg.get("content", "{}"))
        text = content.get("text", "").strip()

        if text and open_id:
            await message_queue.put(
                FeishuMessage(
                    message_id=message_id,
                    open_id=open_id,
                    chat_id=chat_id,
                    text=text,
                )
            )

    return JSONResponse({"code": 0})
