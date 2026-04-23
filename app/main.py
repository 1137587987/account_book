import asyncio
import logging
import os
import sys

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
            try:
                await send_text(msg.open_id, "出了点问题，请稍后再试 🙏")
            except Exception:
                logger.exception("回复错误消息失败: %s", msg.open_id)
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


async def _debug_loop() -> None:
    await init_db()
    print("本地调试模式 — 输入消息模拟飞书对话，exit 退出\n")
    while True:
        try:
            text = input("你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n退出")
            break
        if not text:
            continue
        if text.lower() == "exit":
            break
        async with AsyncSessionLocal() as session:
            reply = await handle_message(session, "local_user", text)
        print(f"Bot：{reply}\n")


if __name__ == "__main__":
    # 飞书配置本地调试时不需要，用占位值避免 pydantic 报错
    os.environ.setdefault("FEISHU_APP_ID", "debug")
    os.environ.setdefault("FEISHU_APP_SECRET", "debug")
    os.environ.setdefault("FEISHU_VERIFICATION_TOKEN", "debug")

    if "--server" in sys.argv:
        import uvicorn
        reload = "--reload" in sys.argv
        uvicorn.run("app.main:app", host="0.0.0.0", port=7880, reload=reload)
    else:
        asyncio.run(_debug_loop())
