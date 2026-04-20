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

    expense_total = sum(r.total for r in rows if r.total > 0)
    income_total = abs(sum(r.total for r in rows if r.total < 0))

    lines = [f"📊 {year}年{month}月账单\n"]
    lines.append(f"支出 ¥{expense_total:.2f}  收入 ¥{income_total:.2f}\n")

    for r in rows:
        sign = "+" if r.total < 0 else "-"
        lines.append(f"  {r.category}  {sign}¥{abs(r.total):.2f}（{r.cnt}笔）")

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

    lines = ["最近记录：\n"]
    for tx in txs:
        sign = "+" if tx.amount < 0 else "-"
        lines.append(
            f"  {tx.spent_at}  {tx.category}  {sign}¥{abs(tx.amount):.2f}  {tx.note}"
        )
    return "\n".join(lines)
