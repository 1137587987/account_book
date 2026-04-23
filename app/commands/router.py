import re
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.commands.query import (
    query_month_summary, query_recent, query_today, query_week_summary,
    add_transaction, get_or_create_user, CATEGORY_EMOJI,
    delete_transaction, modify_transaction,
    set_budget, query_budgets, check_budget_alert, GLOBAL_BUDGET_KEY,
    set_user_email, get_user_email,
)
from app.commands.report import generate_monthly_report
from app.llm.parser import parse_expense

HELP_TEXT = """\
记账 Bot 使用指南：
📧 邮件
  /邮件 xxx@qq.com → 绑定邮箱，每月自动收月报
  /邮件            → 查看当前绑定邮箱


📝 记账（直接发消息）
  星巴克35
  昨天地铁12元
  收到工资15000

✏️ 修改 / 删除
  /删除 上条       → 删最近一笔
  /删除 3          → 删最近第3条
  /修改 上条 金额 50
  /修改 上条 分类 交通
  /修改 上条 备注 打车
  /修改 上条 日期 2026-04-01

💰 预算
  /预算 5000       → 设置月度总预算
  /预算 餐饮 2000  → 设置分类月度上限
  /预算            → 查看所有预算及进度

🔍 查账
  /查账            → 本月汇总
  /查账 今天       → 今日明细
  /查账 最近       → 最近10条
  /查账 最近20     → 最近20条
  /查账 上月       → 上月汇总
  /查账 3月        → 指定月份

📊 /月报          → 本月完整报告
❓ /帮助          → 显示本信息"""


async def handle_message(session: AsyncSession, open_id: str, text: str) -> str:
    text = text.strip()

    if text in ("/帮助", "/help", "帮助"):
        return HELP_TEXT

    if text in ("/月报", "月报"):
        today = date.today()
        user = await get_or_create_user(session, open_id)
        return await generate_monthly_report(session, user.id, today.year, today.month)

    if text.startswith("/邮件") or text.startswith("邮件"):
        args = re.sub(r"^/邮件|^邮件", "", text).strip()
        return await _handle_email(session, open_id, args)

    if text.startswith("/删除") or text.startswith("删除"):
        return await _handle_delete(session, open_id, re.sub(r"^/删除|^删除", "", text).strip())

    if text.startswith("/修改") or text.startswith("修改"):
        return await _handle_modify(session, open_id, re.sub(r"^/修改|^修改", "", text).strip())

    if text.startswith("/预算") or text.startswith("预算"):
        return await _handle_budget(session, open_id, re.sub(r"^/预算|^预算", "", text).strip())

    if text.startswith("/查账") or text.startswith("查账"):
        args = re.sub(r"^/查账|^查账", "", text).strip()
        return await _handle_query(session, open_id, args)

    return await _handle_record(session, open_id, text)


async def _handle_delete(session: AsyncSession, open_id: str, args: str) -> str:
    user = await get_or_create_user(session, open_id)
    n = 1
    if args and args != "上条":
        try:
            n = int(args)
        except ValueError:
            return "格式：/删除 上条  或  /删除 3（删第3条）"
    return await delete_transaction(session, user.id, n)


async def _handle_modify(session: AsyncSession, open_id: str, args: str) -> str:
    user = await get_or_create_user(session, open_id)
    # 格式：上条 金额 50  或  上条 分类 餐饮
    parts = args.split()
    if len(parts) < 3:
        return "格式：/修改 上条 金额 50  或  /修改 上条 分类 交通"
    position = parts[0]
    field = parts[1]
    value = " ".join(parts[2:])
    n = 1
    if position != "上条":
        try:
            n = int(position)
        except ValueError:
            return "格式：/修改 上条 金额 50  或  /修改 3 分类 餐饮"
    return await modify_transaction(session, user.id, field, value, n)


async def _handle_budget(session: AsyncSession, open_id: str, args: str) -> str:
    user = await get_or_create_user(session, open_id)
    if not args:
        return await query_budgets(session, user.id)
    parts = args.split()
    # /预算 5000 → 全局预算
    if len(parts) == 1:
        try:
            amount = float(parts[0])
            return await set_budget(session, user.id, GLOBAL_BUDGET_KEY, amount)
        except ValueError:
            return "格式：/预算 5000（总预算）或 /预算 餐饮 2000（分类预算）"
    # /预算 总计 5000 → 全局预算
    category = parts[0]
    if category in ("总计", "全局", "总"):
        try:
            amount = float(parts[1])
            return await set_budget(session, user.id, GLOBAL_BUDGET_KEY, amount)
        except ValueError:
            return f"金额格式不对：{parts[1]}"
    # /预算 餐饮 2000 → 分类预算
    try:
        amount = float(parts[1])
    except ValueError:
        return f"金额格式不对：{parts[1]}"
    return await set_budget(session, user.id, category, amount)


async def _handle_query(session: AsyncSession, open_id: str, args: str) -> str:
    user = await get_or_create_user(session, open_id)
    today = date.today()

    if not args or args == "本月":
        return await query_month_summary(session, user.id, today.year, today.month)

    if args == "今天":
        return await query_today(session, user.id)

    if args == "上月":
        month = today.month - 1 or 12
        year = today.year if today.month > 1 else today.year - 1
        return await query_month_summary(session, user.id, year, month)

    m = re.match(r"最近(\d+)?$", args)
    if m:
        limit = int(m.group(1)) if m.group(1) else 10
        return await query_recent(session, user.id, limit=min(limit, 50))

    m = re.match(r"(?:(\d{4})年)?(\d{1,2})月", args)
    if m:
        year = int(m.group(1)) if m.group(1) else today.year
        month = int(m.group(2))
        return await query_month_summary(session, user.id, year, month)

    return "格式不对，试试：/查账、/查账 今天、/查账 最近、/查账 3月"


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

    emoji = CATEGORY_EMOJI.get(parsed.category, "✅")
    sign = "+" if parsed.amount < 0 else "-"
    reply = (
        f"{emoji} 已记录\n"
        f"{parsed.category}  {sign}¥{abs(parsed.amount):.2f}\n"
        f"{parsed.date}  {parsed.note}"
    )

    # 记账后检查预算
    if parsed.amount > 0:
        alert = await check_budget_alert(session, user.id, parsed.category)
        if alert:
            reply += f"\n\n{alert}"

    return reply


async def _handle_email(session: AsyncSession, open_id: str, args: str) -> str:
    user = await get_or_create_user(session, open_id)
    if not args:
        return await get_user_email(session, user.id)
    email = args.strip()
    if "@" not in email or "." not in email.split("@")[-1]:
        return f"邮箱格式不对：{email}"
    return await set_user_email(session, user.id, email)
