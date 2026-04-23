from datetime import date
from calendar import monthrange

from sqlalchemy import select, func, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Transaction, User, UserAccount
from app.feishu.client import send_text


async def generate_monthly_report(
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
        return f"📭 {year}年{month}月无消费记录"

    expense_rows = [r for r in rows if r.total > 0]
    income_rows = [r for r in rows if r.total < 0]
    expense_total = sum(r.total for r in expense_rows)
    income_total = abs(sum(r.total for r in income_rows))
    balance = income_total - expense_total

    # 记账天数
    days_in_month = monthrange(year, month)[1]
    day_result = await session.execute(
        select(func.count(func.distinct(Transaction.spent_at))).where(
            Transaction.user_id == user_id,
            extract("year", Transaction.spent_at) == year,
            extract("month", Transaction.spent_at) == month,
        )
    )
    active_days = day_result.scalar() or 0

    lines = [
        f"📊 {year}年{month}月消费报告\n",
        f"支出 ¥{expense_total:.2f}  收入 ¥{income_total:.2f}  结余 {'+'if balance>=0 else ''}¥{balance:.2f}\n",
    ]

    if expense_rows:
        lines.append("支出分类：")
        for r in expense_rows:
            bar = "█" * min(int(r.total / expense_total * 10), 10)
            pct = r.total / expense_total * 100
            lines.append(
                f"  {r.category:4s}  ¥{r.total:>8.2f}  {pct:4.1f}%  {bar}"
            )

    if income_rows:
        lines.append("\n收入分类：")
        for r in income_rows:
            lines.append(f"  {r.category:4s}  +¥{abs(r.total):.2f}（{r.cnt}笔）")

    lines.append(f"\n记账天数：{active_days}/{days_in_month} 天")
    return "\n".join(lines)


async def send_monthly_report_to_all(session: AsyncSession, year: int, month: int) -> None:
    from app.config import settings

    result = await session.execute(
        select(UserAccount).where(UserAccount.platform == "feishu")
    )
    accounts = result.scalars().all()

    for account in accounts:
        report = await generate_monthly_report(session, account.user_id, year, month)
        await send_text(account.platform_user_id, report)

        # 发给用户自己绑定的邮箱
        user_result = await session.execute(select(User).where(User.id == account.user_id))
        user = user_result.scalar_one()
        if user.email and settings.EMAIL_SENDER and settings.EMAIL_PASSWORD:
            _send_email_report(settings, year, month, report, recipient=user.email)


def _send_email_report(settings, year: int, month: int, content: str, recipient: str) -> None:
    try:
        import yagmail
        sender = settings.EMAIL_SENDER
        host = "smtp.qq.com" if sender.endswith("@qq.com") else "smtp.gmail.com"
        yag = yagmail.SMTP(sender, settings.EMAIL_PASSWORD, host=host, port=465)
        yag.send(
            to=recipient,
            subject=f"记账月报 {year}年{month}月",
            contents=content,
        )
    except Exception:
        pass
