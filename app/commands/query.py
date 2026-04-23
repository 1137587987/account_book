from datetime import date
from calendar import monthrange

from sqlalchemy import select, func, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Transaction, User, UserAccount


async def get_or_create_user(session: AsyncSession, open_id: str) -> User:
    result = await session.execute(
        select(UserAccount).where(
            UserAccount.platform == "feishu",
            UserAccount.platform_user_id == open_id,
        )
    )
    account = result.scalar_one_or_none()

    if account:
        result = await session.execute(select(User).where(User.id == account.user_id))
        return result.scalar_one()

    user = User()
    session.add(user)
    await session.flush()

    account = UserAccount(platform="feishu", platform_user_id=open_id, user_id=user.id)
    session.add(account)
    await session.commit()
    await session.refresh(user)
    return user


async def add_transaction(
    session: AsyncSession,
    user_id: int,
    amount: float,
    category: str,
    note: str,
    spent_at: date,
) -> Transaction:
    tx = Transaction(
        user_id=user_id,
        amount=amount,
        category=category,
        note=note,
        spent_at=spent_at,
    )
    session.add(tx)
    await session.commit()
    await session.refresh(tx)
    return tx


CATEGORY_EMOJI = {
    "餐饮": "🍜", "购物": "🛍", "日用": "🧻", "交通": "🚇", "蔬菜": "🥦",
    "水果": "🍎", "零食": "🍿", "运动": "💪", "娱乐": "🎮", "通讯": "📱",
    "服饰": "👕", "美容": "💄", "住房": "🏠", "居家": "🛋", "孩子": "👶",
    "长辈": "👴", "社交": "💬", "旅行": "✈️", "烟酒": "🍷", "数码": "💻",
    "汽车": "🚗", "医疗": "💊", "书籍": "📚", "学习": "🎓", "宠物": "🐶",
    "礼金": "💴", "礼物": "🎁", "办公": "💼", "维修": "🔧", "捐赠": "❤️",
    "彩票": "🎰", "亲友": "👫", "快递": "📦", "工资": "💰", "奖金": "🎉",
    "兼职": "💼", "投资": "📈", "退款": "↩️", "收入": "💰", "其他": "📌",
}


def _fmt_date(d: date) -> str:
    today = date.today()
    delta = (today - d).days
    if delta == 0:
        return "今天"
    if delta == 1:
        return "昨天"
    if delta == 2:
        return "前天"
    if d.year == today.year:
        return f"{d.month}月{d.day}日"
    return str(d)


async def query_month_summary(
    session: AsyncSession, user_id: int, year: int, month: int
) -> str:
    result = await session.execute(
        select(
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("cnt"),
        )
        .where(
            Transaction.user_id == user_id,
            extract("year", Transaction.spent_at) == year,
            extract("month", Transaction.spent_at) == month,
        )
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
    )
    rows = result.all()

    if not rows:
        return f"📭 {year}年{month}月暂无记录"

    expense_rows = [r for r in rows if r.total > 0]
    income_rows = [r for r in rows if r.total < 0]
    expense_total = sum(r.total for r in expense_rows)
    income_total = abs(sum(r.total for r in income_rows))
    balance = income_total - expense_total

    lines = [f"📊 {year}年{month}月账单"]
    lines.append(f"支出 ¥{expense_total:.2f}  收入 ¥{income_total:.2f}  结余 {'+'if balance>=0 else ''}¥{balance:.2f}")
    lines.append("─" * 24)

    if expense_rows:
        for r in expense_rows:
            emoji = CATEGORY_EMOJI.get(r.category, "📌")
            pct = r.total / expense_total * 100 if expense_total else 0
            lines.append(f"{emoji} {r.category}  -¥{r.total:.2f}  {pct:.0f}%（{r.cnt}笔）")

    if income_rows:
        lines.append("")
        for r in income_rows:
            emoji = CATEGORY_EMOJI.get(r.category, "💰")
            lines.append(f"{emoji} {r.category}  +¥{abs(r.total):.2f}（{r.cnt}笔）")

    return "\n".join(lines)


async def query_today(session: AsyncSession, user_id: int) -> str:
    today = date.today()
    result = await session.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id, Transaction.spent_at == today)
        .order_by(Transaction.created_at.desc())
    )
    txs = result.scalars().all()

    if not txs:
        return "📭 今天还没有记录"

    expense = sum(tx.amount for tx in txs if tx.amount > 0)
    income = abs(sum(tx.amount for tx in txs if tx.amount < 0))
    lines = [f"📅 今日账单  共{len(txs)}笔"]
    if expense:
        lines[0] += f"  支出¥{expense:.2f}"
    if income:
        lines[0] += f"  收入¥{income:.2f}"
    lines.append("─" * 24)
    for tx in txs:
        emoji = CATEGORY_EMOJI.get(tx.category, "📌")
        sign = "+" if tx.amount < 0 else "-"
        lines.append(f"{emoji} {tx.category}  {sign}¥{abs(tx.amount):.2f}  {tx.note}")
    return "\n".join(lines)


async def query_recent(session: AsyncSession, user_id: int, limit: int = 10) -> str:
    result = await session.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.spent_at.desc(), Transaction.created_at.desc())
        .limit(limit)
    )
    txs = result.scalars().all()

    if not txs:
        return "📭 暂无记录"

    lines = [f"🕒 最近 {len(txs)} 条记录"]
    lines.append("─" * 24)
    for tx in txs:
        emoji = CATEGORY_EMOJI.get(tx.category, "📌")
        sign = "+" if tx.amount < 0 else "-"
        lines.append(f"{emoji} {_fmt_date(tx.spent_at)}  {tx.category}  {sign}¥{abs(tx.amount):.2f}  {tx.note}")
    return "\n".join(lines)
