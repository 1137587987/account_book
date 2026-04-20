import asyncio
import logging

from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.database import init_db
from app.feishu.webhook import router as feishu_router, message_queue, FeishuMessage
from app.feishu.client import send_text
from app.commands.router import handle_message
from app.database import AsyncSessionLocal
from app.tasks.scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def message_worker() -> None:
    """后台消费队列，处理飞书消息并回复。"""
    while True:
        msg: FeishuMessage = await message_queue.get()
        try:
            async with AsyncSessionLocal() as session:
                reply = await handle_message(session, msg.open_id, msg.text)
            await send_text(msg.open_id, reply)
        except Exception:
            logger.exception("处理消息失败: %s", msg)
            await send_text(msg.open_id, "出了点问题，请稍后再试 🙏")
        finally:
            message_queue.task_done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_scheduler()
    worker = asyncio.create_task(message_worker())
    yield
    worker.cancel()


app = FastAPI(title="飞书记账 Bot", lifespan=lifespan)
app.include_router(feishu_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
