import json
from datetime import date
from dataclasses import dataclass

from app.config import settings
from app.llm.client import get_llm_client

EXPENSE_CATEGORIES = [
    "餐饮", "购物", "日用", "交通", "蔬菜", "水果", "零食", "运动",
    "娱乐", "通讯", "服饰", "美容", "住房", "居家", "孩子", "长辈",
    "社交", "旅行", "烟酒", "数码", "汽车", "医疗", "书籍", "学习",
    "宠物", "礼金", "礼物", "办公", "维修", "捐赠", "彩票", "亲友", "快递", "其他",
]
INCOME_CATEGORIES = ["工资", "奖金", "兼职", "投资", "退款", "收入", "其他"]
CATEGORIES = EXPENSE_CATEGORIES + INCOME_CATEGORIES

PARSE_PROMPT = """\
从用户消息中提取消费或收入记录，返回 JSON 对象。

规则：
- amount: 数字，支出为正数，收入/退款为负数
- category: 从 [{categories}] 中选最合适的一个
- note: 简短描述（保留原始关键词）
- date: YYYY-MM-DD 格式，消息未提及日期则用今天

如果消息不含任何金额数字，返回：{{"error": "no_amount"}}
只返回 JSON，不要其他内容。

今天日期：{today}
用户消息：{message}"""


@dataclass
class ParsedExpense:
    amount: float
    category: str
    note: str
    date: date


async def parse_expense(message: str) -> ParsedExpense | None:
    today = date.today().isoformat()
    prompt = PARSE_PROMPT.format(
        categories="、".join(CATEGORIES),
        today=today,
        message=message,
    )

    client = get_llm_client()
    response = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    data = json.loads(raw)

    if "error" in data:
        return None

    spent_date = date.fromisoformat(data.get("date", today))
    return ParsedExpense(
        amount=float(data["amount"]),
        category=data.get("category", "其他"),
        note=data.get("note", message[:50]),
        date=spent_date,
    )
