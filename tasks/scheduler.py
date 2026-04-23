import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.database import AsyncSessionLocal
from app.commands.report import send_monthly_report_to_all

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


async def _monthly_report_job() -> None:
    today = date.today()
    # 发上个月的报告（每月1日触发）
    year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    logger.info("发送 %d年%d月 月报", year, month)
    async with AsyncSessionLocal() as session:
        await send_monthly_report_to_all(session, year, month)


def start_scheduler() -> None:
    # 每月1日 09:00 发送上月报告
    scheduler.add_job(_monthly_report_job, "cron", day=1, hour=9, minute=0)
    scheduler.start()
    logger.info("定时任务已启动")
