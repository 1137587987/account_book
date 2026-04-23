from datetime import date, timedelta
from calendar import monthrange

from sqlalchemy import select, func, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Transaction, User, UserAccount, Budget


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


async def set_user_email(session: AsyncSession, user_id: int, email: str) -> str:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()
    user.email = email
    await session.commit()
    return f"✅ 已绑定邮箱 {email}\n每月1日自动发送月报到该邮箱"


async def get_user_email(session: AsyncSession, user_id: int) -> str:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()
    if user.email:
        return f"📧 当前绑定邮箱：{user.email}\n发送「/邮件 新邮箱」可以修改"
    return "未绑定邮箱\n发送「/邮件 xxx@qq.com」绑定后可接收月报"


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


async def delete_transaction(session: AsyncSession, user_id: int, n: int = 1) -> str:
    result = await session.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc())
        .limit(n)
    )
    txs = result.scalars().all()
    if len(txs) < n:
        return f"找不到第 {n} 条记录"
    tx = txs[-1]
    emoji = CATEGORY_EMOJI.get(tx.category, "📌")
    sign = "+" if tx.amount < 0 else "-"
    desc = f"{emoji} {tx.category}  {sign}¥{abs(tx.amount):.2f}  {tx.note}  {_fmt_date(tx.spent_at)}"
    await session.delete(tx)
    await session.commit()
    return f"✅ 已删除\n{desc}"


async def modify_transaction(
    session: AsyncSession, user_id: int, field: str, value: str, n: int = 1
) -> str:
    result = await session.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc())
        .limit(n)
    )
    txs = result.scalars().all()
    if len(txs) < n:
        return f"找不到第 {n} 条记录"
    tx = txs[-1]

    if field in ("金额", "amount"):
        try:
            tx.amount = float(value)
        except ValueError:
            return f"金额格式不对：{value}"
    elif field in ("分类", "category"):
        tx.category = value
    elif field in ("备注", "note"):
        tx.note = value
    elif field in ("日期", "date"):
        try:
            tx.spent_at = date.fromisoformat(value)
        except ValueError:
            return f"日期格式不对，请用 YYYY-MM-DD：{value}"
    else:
        return f"不支持修改字段「{field}」，可改：金额 / 分类 / 备注 / 日期"

    await session.commit()
    emoji = CATEGORY_EMOJI.get(tx.category, "📌")
    sign = "+" if tx.amount < 0 else "-"
    return f"✅ 已修改\n{emoji} {tx.category}  {sign}¥{abs(tx.amount):.2f}  {tx.note}  {_fmt_date(tx.spent_at)}"


GLOBAL_BUDGET_KEY = "__total__"


async def set_budget(session: AsyncSession, user_id: int, category: str, amount: float) -> str:
    result = await session.execute(
        select(Budget).where(Budget.user_id == user_id, Budget.category == category)
    )
    budget = result.scalar_one_or_none()
    if budget:
        budget.amount = amount
    else:
        session.add(Budget(user_id=user_id, category=category, amount=amount))
    await session.commit()
    if category == GLOBAL_BUDGET_KEY:
        return f"✅ 已设置月度总预算 ¥{amount:.0f}"
    emoji = CATEGORY_EMOJI.get(category, "📌")
    return f"✅ 已设置 {emoji} {category} 月度预算 ¥{amount:.0f}"


async def query_budgets(session: AsyncSession, user_id: int) -> str:
    today = date.today()
    result = await session.execute(
        select(Budget).where(Budget.user_id == user_id)
    )
    budgets = result.scalars().all()
    if not budgets:
        return "还没有设置预算\n发送「/预算 餐饮 2000」设置分类预算\n发送「/预算 总计 5000」设置月度总预算"

    # 本月实际支出
    total_spent = await _get_month_expense_total(session, user_id, today.year, today.month)
    spent_map: dict[str, float] = {}
    for b in budgets:
        if b.category == GLOBAL_BUDGET_KEY:
            spent_map[b.category] = total_spent
            continue
        r = await session.execute(
            select(func.sum(Transaction.amount)).where(
                Transaction.user_id == user_id,
                Transaction.category == b.category,
                Transaction.amount > 0,
                extract("year", Transaction.spent_at) == today.year,
                extract("month", Transaction.spent_at) == today.month,
            )
        )
        spent_map[b.category] = float(r.scalar() or 0)

    lines = [f"📋 本月预算 ({today.year}年{today.month}月)"]
    lines.append("─" * 24)

    # 全局预算排最前
    global_budget = next((b for b in budgets if b.category == GLOBAL_BUDGET_KEY), None)
    if global_budget:
        spent = spent_map[GLOBAL_BUDGET_KEY]
        g_amount = float(global_budget.amount)
        pct = spent / g_amount * 100 if g_amount else 0
        filled = min(int(pct / 10), 10)
        bar = "█" * filled + "░" * (10 - filled)
        status = "🚨" if pct >= 100 else ("⚠️" if pct >= 80 else "")
        lines.append(f"💼 月度总计  ¥{spent:.0f}/¥{g_amount:.0f}  {pct:.0f}%  {status}")
        lines.append(f"  {bar}")
        lines.append("")

    for b in sorted(budgets, key=lambda x: x.category):
        if b.category == GLOBAL_BUDGET_KEY:
            continue
        spent = spent_map.get(b.category, 0)
        b_amount = float(b.amount)
        pct = spent / b_amount * 100 if b_amount else 0
        filled = min(int(pct / 10), 10)
        bar = "█" * filled + "░" * (10 - filled)
        emoji = CATEGORY_EMOJI.get(b.category, "📌")
        status = "🚨" if pct >= 100 else ("⚠️" if pct >= 80 else "")
        lines.append(f"{emoji} {b.category}  ¥{spent:.0f}/¥{b_amount:.0f}  {pct:.0f}%  {status}")
        lines.append(f"  {bar}")
    return "\n".join(lines)


async def check_budget_alert(session: AsyncSession, user_id: int, category: str) -> str | None:
    today = date.today()
    alerts = []

    # 检查分类预算
    if category not in ("收入", "工资", "奖金", "兼职", "投资", "退款"):
        result = await session.execute(
            select(Budget).where(Budget.user_id == user_id, Budget.category == category)
        )
        cat_budget = result.scalar_one_or_none()
        if cat_budget:
            r = await session.execute(
                select(func.sum(Transaction.amount)).where(
                    Transaction.user_id == user_id,
                    Transaction.category == category,
                    Transaction.amount > 0,
                    extract("year", Transaction.spent_at) == today.year,
                    extract("month", Transaction.spent_at) == today.month,
                )
            )
            spent = float(r.scalar() or 0)
            c_amount = float(cat_budget.amount)
            pct = spent / c_amount * 100 if c_amount else 0
            remaining = c_amount - spent
            if pct >= 100:
                alerts.append(f"🚨 {category}已超出预算！已花 ¥{spent:.0f}，超出 ¥{abs(remaining):.0f}")
            elif pct >= 80:
                alerts.append(f"⚠️ {category}预算剩余 ¥{remaining:.0f}（已用 {pct:.0f}%）")

    # 检查全局预算
    result = await session.execute(
        select(Budget).where(Budget.user_id == user_id, Budget.category == GLOBAL_BUDGET_KEY)
    )
    global_budget = result.scalar_one_or_none()
    if global_budget:
        total_spent = await _get_month_expense_total(session, user_id, today.year, today.month)
        g_amount = float(global_budget.amount)
        pct = total_spent / g_amount * 100 if g_amount else 0
        remaining = g_amount - total_spent
        if pct >= 100:
            alerts.append(f"🚨 月度总预算已超出！已花 ¥{total_spent:.0f}，超出 ¥{abs(remaining):.0f}")
        elif pct >= 80:
            alerts.append(f"⚠️ 月度总预算剩余 ¥{remaining:.0f}（已用 {pct:.0f}%）")

    return "\n".join(alerts) if alerts else None


async def _get_month_expense_total(session: AsyncSession, user_id: int, year: int, month: int) -> float:
    r = await session.execute(
        select(func.sum(Transaction.amount)).where(
            Transaction.user_id == user_id,
            Transaction.amount > 0,
            extract("year", Transaction.spent_at) == year,
            extract("month", Transaction.spent_at) == month,
        )
    )
    return float(r.scalar() or 0)


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

    # 预算数据
    budget_result = await session.execute(
        select(Budget).where(Budget.user_id == user_id)
    )
    budget_map: dict[str, float] = {b.category: float(b.amount) for b in budget_result.scalars().all()}
    global_budget = budget_map.get(GLOBAL_BUDGET_KEY)

    # 同比上月
    prev_month = month - 1 or 12
    prev_year = year if month > 1 else year - 1
    prev_total = await _get_month_expense_total(session, user_id, prev_year, prev_month)
    if prev_total > 0:
        diff = expense_total - prev_total
        compare = f"vs 上月 {'+'if diff>=0 else ''}¥{diff:.0f}（{diff/prev_total*100:+.1f}%）"
    else:
        compare = ""

    # 拉取所有明细，按分类分组
    detail_result = await session.execute(
        select(Transaction)
        .where(
            Transaction.user_id == user_id,
            extract("year", Transaction.spent_at) == year,
            extract("month", Transaction.spent_at) == month,
        )
        .order_by(Transaction.category, Transaction.spent_at.desc())
    )
    all_txs = detail_result.scalars().all()
    detail_map: dict[str, list[Transaction]] = {}
    for tx in all_txs:
        detail_map.setdefault(tx.category, []).append(tx)

    lines = [f"📊 {year}年{month}月账单"]
    lines.append(f"支出 ¥{expense_total:.2f}  收入 ¥{income_total:.2f}  结余 {'+'if balance>=0 else ''}¥{balance:.2f}")

    # 总预算进度
    if global_budget:
        g_pct = float(expense_total) / global_budget * 100 if global_budget else 0
        filled = min(int(g_pct / 10), 10)
        g_bar = "█" * filled + "░" * (10 - filled)
        g_status = " 🚨超出" if g_pct >= 100 else (" ⚠️将超" if g_pct >= 80 else "")
        lines.append(f"月预算 ¥{global_budget:.0f}  已用{g_pct:.0f}%{g_status}  {g_bar}")

    if compare:
        lines.append(compare)
    lines.append("─" * 24)

    if expense_rows:
        for r in expense_rows:
            emoji = CATEGORY_EMOJI.get(r.category, "📌")
            pct = r.total / expense_total * 100 if expense_total else 0
            cat_budget = budget_map.get(r.category)
            if cat_budget:
                b_pct = float(r.total) / cat_budget * 100
                b_status = "🚨" if b_pct >= 100 else ("⚠️" if b_pct >= 80 else "✅")
                budget_tag = f"  预算¥{cat_budget:.0f} {b_pct:.0f}% {b_status}"
            else:
                budget_tag = ""
            lines.append(f"{emoji} {r.category}  -¥{r.total:.2f}  {pct:.0f}%（{r.cnt}笔）{budget_tag}")
            for tx in detail_map.get(r.category, []):
                sign = "+" if tx.amount < 0 else "-"
                lines.append(f"  · {_fmt_date(tx.spent_at)}  {tx.note}  {sign}¥{abs(tx.amount):.2f}")

    if income_rows:
        lines.append("")
        for r in income_rows:
            emoji = CATEGORY_EMOJI.get(r.category, "💰")
            lines.append(f"{emoji} {r.category}  +¥{abs(r.total):.2f}（{r.cnt}笔）")
            for tx in detail_map.get(r.category, []):
                sign = "+" if tx.amount < 0 else "-"
                lines.append(f"  · {_fmt_date(tx.spent_at)}  {tx.note}  {sign}¥{abs(tx.amount):.2f}")

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
    for i, tx in enumerate(txs, 1):
        emoji = CATEGORY_EMOJI.get(tx.category, "📌")
        sign = "+" if tx.amount < 0 else "-"
        lines.append(f"{i}. {emoji} {_fmt_date(tx.spent_at)}  {tx.category}  {sign}¥{abs(tx.amount):.2f}  {tx.note}")
    return "\n".join(lines)


async def query_week_summary(session: AsyncSession, user_id: int, week_start: date) -> str:
    week_end = week_start + timedelta(days=6)
    result = await session.execute(
        select(
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("cnt"),
        )
        .where(
            Transaction.user_id == user_id,
            Transaction.spent_at >= week_start,
            Transaction.spent_at <= week_end,
        )
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
    )
    rows = result.all()

    if not rows:
        return f"📭 {week_start.month}月{week_start.day}日～{week_end.month}月{week_end.day}日暂无记录"

    expense_rows = [r for r in rows if r.total > 0]
    income_rows = [r for r in rows if r.total < 0]
    expense_total = sum(r.total for r in expense_rows)
    income_total = abs(sum(r.total for r in income_rows))

    lines = [f"📊 周报 {week_start.month}/{week_start.day}～{week_end.month}/{week_end.day}"]
    lines.append(f"支出 ¥{expense_total:.2f}  收入 ¥{income_total:.2f}")
    lines.append("─" * 24)
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
