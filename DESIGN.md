# 飞书记账 MVP — 设计文档

**Date:** 2026-04-20
**Branch:** master
**Author:** zoujiang
**Mode:** Builder (自用工具，兼顾朋友使用)

---

## 问题陈述

用户在微信支付、支付宝、现金、饿了么等多个平台消费，数据分散，无法汇总。现有记账 App 要求打开 App、手动选分类，坚持不了三天。

**核心洞察：** 真正的零摩擦不是"更容易的输入"，而是"在你已经在的地方输入"。用户全天在飞书，顺手发一条消息完成记录，和"打开 App"之间差了一个量级的摩擦。

---

## 已确认前提

1. **飞书是主入口** — 用户日常在飞书，官方 Bot API，稳定合法
2. **AI 自动分类** — 用户不手动选分类，说"星巴克 35"自动归类
3. **账单导入延后** — 微信/支付宝没有个人账单 API，CSV 导入移至 Phase 2
4. **自有服务器部署** — NAS/自有主机，Docker Compose，无需付费云服务
5. **多用户支持** — 自己和朋友都能用，数据独立隔离
6. **收支双向记录** — amount 正数=支出，负数=收入/退款

---

## 系统架构

```
用户手机 (飞书)
    │
    │ 发消息："星巴克35"
    │ 发消息："/查账 本月"
    │ 上传：微信账单.csv
    ↓
飞书开放平台 (官方 Webhook)
    │
    │ POST /webhook/feishu
    ↓
┌─────────────────────────────────────────┐
│            FastAPI 服务                  │
│                                         │
│  ┌──────────────┐                       │
│  │ Webhook 层   │ → 立即返回 200         │
│  │ (asyncio 队列│   异步处理             │
│  └──────┬───────┘                       │
│         │                               │
│  ┌──────▼───────────────────────────┐   │
│  │  消息路由                         │   │
│  │  - 普通文本 → AI 解析记账         │   │
│  │  - /命令    → 命令处理器          │   │
│  │  - 文件上传 → CSV 导入            │   │
│  └──────┬───────────────────────────┘   │
│         │                               │
│  ┌──────▼───────────────────────────┐   │
│  │  LLM 解析层 (openai SDK)          │   │
│  │  可配置: OpenAI / DeepSeek /      │   │
│  │          阿里百炼 / 任意兼容接口  │   │
│  └──────┬───────────────────────────┘   │
│         │                               │
│  ┌──────▼───────────────────────────┐   │
│  │  数据库层 (SQLite + SQLAlchemy)   │   │
│  │  users / user_accounts /          │   │
│  │  transactions / categories        │   │
│  └──────┬───────────────────────────┘   │
│         │                               │
│  ┌──────▼───────────────────────────┐   │
│  │  报告生成器 + APScheduler         │   │
│  │  月底定时 → 飞书推送 + 邮件       │   │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
    ↓
    自有服务器 (NAS/主机)
    Docker Compose + Nginx + certbot (HTTPS)
```

---

## 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 语言 | Python 3.12 | 生态最好，SDK 齐全 |
| Web 框架 | FastAPI + uvicorn | 异步，性能好 |
| AI 解析 | `openai` SDK | 统一接口，可切换任意兼容模型 |
| 数据库 | SQLite + SQLAlchemy (aiosqlite) | MVP 够用，需要时无缝迁移 PG |
| 飞书接入 | 飞书开放平台 Bot API (lark-oapi) | 官方稳定，免费 |
| 定时任务 | APScheduler | 内嵌，无需 Redis |
| 邮件 | yagmail | 标准 SMTP |
| 部署 | Docker Compose + Nginx | 一键起服务 |

### LLM 提供商配置（.env）

```env
# OpenAI
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=gpt-4o-mini

# DeepSeek
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=deepseek-chat

# 阿里百炼（通义千问）
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=qwen-turbo
```

---

## 数据库设计

```sql
-- 用户表
CREATE TABLE users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT,
    email       TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 平台账号绑定（一用户可绑多平台）
CREATE TABLE user_accounts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER REFERENCES users(id),
    platform         TEXT,           -- 'feishu' | 'wecom'
    platform_user_id TEXT,
    UNIQUE(platform, platform_user_id)
);

-- 收支记录（正数=支出，负数=收入/退款）
CREATE TABLE transactions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER REFERENCES users(id),
    amount       DECIMAL(10,2) NOT NULL,   -- 正=支出，负=收入
    category     TEXT,                      -- AI 归类结果
    note         TEXT,                      -- 原始描述
    source       TEXT DEFAULT 'manual',     -- 'manual'（MVP 阶段仅手动）
    external_id  TEXT,                      -- 交易单号，用于去重
    spent_at     DATE NOT NULL,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, external_id)            -- 防止重复导入
);

-- 分类表
CREATE TABLE categories (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT UNIQUE NOT NULL,
    icon  TEXT
);
```

**默认分类：** 餐饮🍜 / 交通🚇 / 购物🛒 / 娱乐🎮 / 医疗🏥 / 居家🏠 / 教育📚 / 收入💰 / 其他📦

---

## 项目结构

```
accout_book/
├── DESIGN.md                   # 本文件
├── TODOS.md
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── nginx/
│   └── default.conf
├── app/
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 环境变量 (pydantic-settings)
│   ├── database.py             # SQLAlchemy 异步引擎
│   ├── models.py               # ORM 模型
│   │
│   ├── feishu/
│   │   ├── client.py           # 飞书 API 客户端（发消息/卡片）
│   │   ├── webhook.py          # Webhook 接收 + asyncio 队列
│   │   └── card.py             # 飞书消息卡片模板
│   │
│   ├── llm/
│   │   ├── client.py           # openai.AsyncOpenAI，读 LLM_BASE_URL
│   │   └── parser.py           # 自然语言 → {amount, category, note, date}
│   │
│   ├── commands/
│   │   ├── router.py           # 命令路由 (/查账 /月报 /统计 /帮助)
│   │   ├── query.py            # 查账逻辑
│   │   └── report.py           # 月报生成
│   │
│   └── tasks/
│       └── scheduler.py        # APScheduler 月底定时任务
│
└── tests/
    ├── test_llm_parser.py      # LLM 解析（mock openai）
    ├── test_commands.py        # 查账命令逻辑
    └── test_webhook.py         # Webhook 处理 + 防重
```

---

## 核心功能规格

### 1. 自然语言记账

```python
PARSE_PROMPT = """
从用户消息中提取消费或收入记录，返回 JSON。

规则：
- amount: 数字，支出为正，收入/退款为负
- category: 从 [餐饮,交通,购物,娱乐,医疗,居家,教育,收入,其他] 中选一个
- note: 简短描述
- date: YYYY-MM-DD，未提及则用今天

如果消息不含金额，返回：{"error": "no_amount"}

今天日期：{today}
用户消息：{message}
"""
```

**示例对话：**
```
用户：星巴克35
Bot：✅ 已记录
     ☕ 餐饮 ¥35.00
     2026-04-20 | 星巴克

用户：昨天地铁12
Bot：✅ 已记录
     🚇 交通 ¥12.00
     2026-04-19 | 地铁

用户：收到工资 15000
Bot：✅ 已记录
     💰 收入 +¥15,000.00
     2026-04-20 | 工资
```

### 2. 查账命令

```
/查账          → 本月消费汇总
/查账 本周      → 本周明细
/查账 餐饮      → 餐饮分类明细
/查账 3月       → 3月账单
/帮助           → 命令列表
```

### 3. 月报（每月 1 日自动推送）

```
📊 3月消费报告

支出：¥6,234.00  收入：¥15,000.00  结余：+¥8,766.00
vs 上月支出：+8.3%

支出分类：
🍜 餐饮    ¥2,100  33.7%  ████████
🛒 购物    ¥1,800  28.9%  ███████
🚇 交通    ¥  800  12.8%  ███
🎮 娱乐    ¥  600   9.6%  ██
📦 其他    ¥  934  15.0%  ████

最贵一笔：购物 ¥580（3月15日）
记账天数：28/31 天
```

---

## 飞书 Bot 配置步骤

```
1. 飞书开放平台 → 创建应用（自建应用）
2. 配置 Webhook URL: https://your-domain.com/webhook/feishu
3. 申请权限：im:message.receive_v1 + im:message
4. 发布应用
5. 用户搜索 Bot 名称添加好友即可使用
```

---

## 部署配置

```yaml
# docker-compose.yml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data         # SQLite 持久化
    env_file: .env
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx:/etc/nginx/conf.d
      - ./ssl:/etc/letsencrypt
    restart: unless-stopped
```

---

## 风险和失败模式

| 风险 | 缓解方案 |
|------|---------|
| LLM 解析错误分类 | 允许 `/修改 上条 餐饮` 纠正 |
| 飞书 Webhook 3 秒超时 | asyncio 队列，立即返回 200，异步回复 |
| 飞书消息重试重复处理 | 消息 ID 幂等检查 |

---

## 开发顺序

```
Week 1:
  Day 1-2: 飞书 Bot 基础（Webhook 接收 + 消息回复）
  Day 3-4: LLM 解析 + 数据库存储
  Day 5:   /查账 命令

Week 2:
  Day 1-2: CSV 导入（微信 + 支付宝）
  Day 3:   月报生成 + 定时任务
  Day 4:   邮件推送
  Day 5:   Docker 部署 + Nginx HTTPS

Week 3:
  测试 + 找朋友用 + 修 Bug
```

---

## NOT in scope（MVP）

- 自动抓取微信/支付宝账单（无官方 API，Phase 2 考虑）
- 微信/支付宝 CSV 账单导入（Phase 2）
- Web 管理界面（纯 Bot 够用）
- 企业微信接入（架构支持扩展，按需添加）
- 预算设置和超支提醒（先把记录做好）
- 数据导出 PDF
- iOS 快捷指令联动

---

*文档随项目进展同步更新。*
