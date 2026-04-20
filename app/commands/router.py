import re
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.commands.query import query_month_summary, query_recent
from app.commands.report import generate_monthly_report
from app.llm.parser import parse_expense
from app.commands.query import add_transaction, get_or_create_user

HELP_TEXT = """\
记账 Bot 使用指南：

📝 记账（直接发消息）
  星巴克35
  昨天地铁12
  收到工资15000

🔍 查账
  /查账         → 本月汇总
  /查账 最近    → 最近10条
  /查账 3月     → 指定月份

📊 /月报       → 本月完整报告
❓ /帮助       → 显示本信息"""


async def handle_message(session: AsyncSession, open_id: str, text: str) -> str:
    text = text.strip()

    if text in ("/帮助", "/help", "帮助"):
        return HELP_TEXT

    if text == "/月报":
        today = date.today()
        user = await get_or_create_user(session, open_id)
        return await generate_monthly_report(session, user.id, today.year, today.month)

    if text.startswith("/查账"):
        return await _handle_query(session, open_id, text[3:].strip())

    # 默认当作记账消息处理
    return await _handle_record(session, open_id, text)


async def _handle_query(session: AsyncSession, open_id: str, args: str) -> str:
    user = await get_or_create_user(session, open_id)
    today = date.today()

    if not args or args == "本月":
        return await query_month_summary(session, user.id, today.year, today.month)

    if args == "最近":
        return await query_recent(session, user.id)

    # 匹配 "3月" 或 "2025年3月"
    m = re.match(r"(?:(\d{4})年)?(\d{1,2})月", args)
    if m:
        year = int(m.group(1)) if m.group(1) else today.year
        month = int(m.group(2))
        return await query_month_summary(session, user.id, year, month)

    return "格式不对，试试：/查账、/查账 最近、/查账 3月"


async def _handle_record(session: AsyncSession, open_id: str, text: str) -> str:
    parsed = await parse_expense(text)
    if parsed is None:
        return "没识别到金额，试试：\"星巴克35\" 或 \"地铁12\""

    user = await get_or_create_user(session, open_id)
    await add_transaction(
        session,
        user_id=user.id,
        amount=parsed.amount,
        category=parsed.category,
        note=parsed.note,
        spent_at=parsed.date,
    )

    sign = "+" if parsed.amount < 0 else "-"
    emoji = "💰" if parsed.amount < 0 else "✅"
    return (
        f"{emoji} 已记录\n"
        f"{parsed.category}  {sign}¥{abs(parsed.amount):.2f}\n"
        f"{parsed.date}  {parsed.note}"
    )
