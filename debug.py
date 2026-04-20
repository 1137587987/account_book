"""
本地调试入口 — 无需飞书、无需 Docker，直接命令行模拟对话。

用法：
  python debug.py

依赖 .env 里的 LLM 配置（FEISHU_* 可留空）。
"""

import asyncio
import os

# 飞书配置可留空，本地调试不需要
os.environ.setdefault("FEISHU_APP_ID", "debug")
os.environ.setdefault("FEISHU_APP_SECRET", "debug")
os.environ.setdefault("FEISHU_VERIFICATION_TOKEN", "debug")

from app.database import init_db, AsyncSessionLocal
from app.commands.router import handle_message

OPEN_ID = "local_debug_user"


async def main() -> None:
    await init_db()
    print("飞书记账 Bot — 本地调试模式")
    print("输入消息模拟对话，输入 exit 退出\n")

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
            reply = await handle_message(session, OPEN_ID, text)

        print(f"Bot：{reply}\n")


if __name__ == "__main__":
    asyncio.run(main())
