from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database import AsyncSessionLocal
from app.commands.report import send_monthly_report_to_all
from app.commands.query import query_week_summary
from app.feishu.client import send_text
from app.models import UserAccount
from sqlalchemy import select


async def _send_last_month_report() -> None:
    today = date.today()
    month = today.month - 1 or 12
    year = today.year if today.month > 1 else today.year - 1
    async with AsyncSessionLocal() as session:
        await send_monthly_report_to_all(session, year, month)


async def _send_weekly_report() -> None:
    today = date.today()
    week_start = today - timedelta(days=today.weekday() + 7)  # 上周一
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserAccount).where(UserAccount.platform == "feishu")
        )
        accounts = result.scalars().all()
        for account in accounts:
            report = await query_week_summary(session, account.user_id, week_start)
            await send_text(account.platform_user_id, report)


def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    # 每月1日 09:00 发上月报告
    scheduler.add_job(
        _send_last_month_report,
        CronTrigger(day=1, hour=9, minute=0, timezone="Asia/Shanghai"),
    )
    # 每周一 09:00 发上周周报
    scheduler.add_job(
        _send_weekly_report,
        CronTrigger(day_of_week="mon", hour=9, minute=0, timezone="Asia/Shanghai"),
    )
    scheduler.start()
    return scheduler
