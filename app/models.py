from datetime import datetime, date
from sqlalchemy import Integer, String, Numeric, Date, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    accounts: Mapped[list["UserAccount"]] = relationship(back_populates="user")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user")


class UserAccount(Base):
    __tablename__ = "user_accounts"
    __table_args__ = (UniqueConstraint("platform", "platform_user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    platform: Mapped[str] = mapped_column(String(32))        # 'feishu'
    platform_user_id: Mapped[str] = mapped_column(String(128))

    user: Mapped["User"] = relationship(back_populates="accounts")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[float] = mapped_column(Numeric(10, 2))    # 正=支出，负=收入
    category: Mapped[str | None] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(String(256))
    source: Mapped[str] = mapped_column(String(32), default="manual")
    spent_at: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    user: Mapped["User"] = relationship(back_populates="transactions")
