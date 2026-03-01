#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 持久化记忆系统 - 统一查询接口
支持：SQLite 结构化查询 + ChromaDB 向量语义检索 + Markdown 文件加载
用法：
  python3 memory_query.py --query "西藏项目API问题"
  python3 memory_query.py --init        # 初始化数据库并导入所有记忆
  python3 memory_query.py --add-episode # 添加今日情境记忆
  python3 memory_query.py --stats       # 显示记忆统计
"""

import os
import sys
import json
import sqlite3
import argparse
import datetime
from pathlib import Path

# ─────────────────────────────────────────────
# 配置
# ─────────────────────────────────────────────
MEMORY_ROOT = Path.home() / "ai_memory"
DB_DIR      = MEMORY_ROOT / "db"
SQLITE_PATH = DB_DIR / "memory.db"
CHROMA_DIR  = DB_DIR / "chroma"

MEMORY_FILES = {
    "core1":       MEMORY_ROOT / "core1.md",
    "core2":       MEMORY_ROOT / "core2.md",
    "preferences": MEMORY_ROOT / "preferences.md",
    "failures":    MEMORY_ROOT / "failures.md",
    "graph":       MEMORY_ROOT / "graph.md",
    "today":       MEMORY_ROOT / "today.md",
}

EPISODE_DIR  = MEMORY_ROOT / "episodes"
PROJECT_DIR  = MEMORY_ROOT / "projects"
MODULES_DIR  = MEMORY_ROOT / "modules"

# ─────────────────────────────────────────────
# SQLite 初始化
# ─────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS core_memory (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    layer        TEXT NOT NULL,          -- core1 / core2 / module / project
    module       TEXT NOT NULL,          -- 模块名
    content      TEXT NOT NULL,          -- 内容
    frequency    TEXT DEFAULT 'mid',     -- always / high / mid / low
    confidence   INTEGER DEFAULT 3,      -- 1-5 星
    anchors      TEXT DEFAULT '',        -- 触发词，逗号分隔
    created_at   TEXT DEFAULT (datetime('now','localtime')),
    updated_at   TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS relationships (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_from  TEXT NOT NULL,
    entity_to    TEXT NOT NULL,
    relation     TEXT NOT NULL,          -- 关系类型
    note         TEXT DEFAULT '',
    created_at   TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS preferences (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category     TEXT NOT NULL,          -- 沟通/技术/工作习惯
    key          TEXT NOT NULL,
    value        TEXT NOT NULL,
    confidence   INTEGER DEFAULT 3,
    updated_at   TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(category, key)
);

CREATE TABLE IF NOT EXISTS failures (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code         TEXT UNIQUE,            -- F001, F002...
    project      TEXT DEFAULT '',
    symptom      TEXT NOT NULL,
    root_cause   TEXT NOT NULL,
    fix          TEXT NOT NULL,
    lesson       TEXT NOT NULL,
    tags         TEXT DEFAULT '',
    date         TEXT DEFAULT (date('now','localtime'))
);

CREATE TABLE IF NOT EXISTS episodes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT NOT NULL,
    title        TEXT NOT NULL,
    summary      TEXT NOT NULL,
    anchors      TEXT DEFAULT '',
    file_path    TEXT DEFAULT '',
    created_at   TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS todos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task         TEXT NOT NULL,
    project      TEXT DEFAULT '',
    priority     INTEGER DEFAULT 3,      -- 1=紧急 5=低
    status       TEXT DEFAULT 'open',    -- open / done / blocked
    due_date     TEXT DEFAULT '',
    created_at   TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS api_keys (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    provider     TEXT UNIQUE NOT NULL,
    key_hint     TEXT NOT NULL,          -- 只存前8位+***
    balance      TEXT DEFAULT 'unknown',
    priority     INTEGER DEFAULT 5,
    updated_at   TEXT DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_core_layer    ON core_memory(layer);
CREATE INDEX IF NOT EXISTS idx_core_freq     ON core_memory(frequency);
CREATE INDEX IF NOT EXISTS idx_failures_code ON failures(code);
CREATE INDEX IF NOT EXISTS idx_episodes_date ON episodes(date);
CREATE INDEX IF NOT EXISTS idx_todos_status  ON todos(status);
"""

def get_db():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


# ─────────────────────────────────────────────
# ChromaDB 向量检索（可选，若未安装则降级）
# ─────────────────────────────────────────────
def get_chroma_client():
    try:
        import chromadb
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        return client
    except ImportError:
        return None

def chroma_add(collection_name: str, doc_id: str, text: str, metadata: dict = None):
    client = get_chroma_client()
    if not client:
        return False
    try:
        col = client.get_or_create_collection(collection_name)
        col.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata or {}]
        )
        return True
    except Exception as e:
        print(f"[ChromaDB] 写入失败: {e}", file=sys.stderr)
        return False

def chroma_query(collection_name: str, query_text: str, n_results: int = 5):
    client = get_chroma_client()
    if not client:
        return []
    try:
        col = client.get_or_create_collection(collection_name)
        results = col.query(query_texts=[query_text], n_results=n_results)
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        return list(zip(docs, metas))
    except Exception as e:
        print(f"[ChromaDB] 查询失败: {e}", file=sys.stderr)
        return []


# ─────────────────────────────────────────────
# 记忆导入：将 Markdown 文件内容写入数据库
# ─────────────────────────────────────────────
def import_markdown_to_db(conn):
    """将所有 Markdown 记忆文件导入 SQLite + ChromaDB"""
    cursor = conn.cursor()
    imported = 0

    for layer, fpath in MEMORY_FILES.items():
        if not fpath.exists():
            continue
        content = fpath.read_text(encoding="utf-8")
        # 提取 anchors
        anchors = ""
        for line in content.splitlines():
            if "anchors:" in line:
                anchors = line.split("anchors:")[-1].strip().rstrip("-->").strip()
                break
        cursor.execute("""
            INSERT OR REPLACE INTO core_memory (layer, module, content, frequency, anchors)
            VALUES (?, ?, ?, 'always', ?)
        """, (layer, fpath.name, content, anchors))
        chroma_add("memory_files", f"{layer}_{fpath.name}",
                   content[:2000],  # 向量化前2000字
                   {"layer": layer, "file": str(fpath)})
        imported += 1

    # 导入 projects/
    for fpath in PROJECT_DIR.glob("*.md") if PROJECT_DIR.exists() else []:
        content = fpath.read_text(encoding="utf-8")
        cursor.execute("""
            INSERT OR REPLACE INTO core_memory (layer, module, content, frequency)
            VALUES ('project', ?, ?, 'high')
        """, (fpath.stem, content))
        chroma_add("memory_files", f"project_{fpath.stem}", content[:2000],
                   {"layer": "project", "file": str(fpath)})
        imported += 1

    # 导入 episodes/
    for fpath in sorted(EPISODE_DIR.glob("*.md")) if EPISODE_DIR.exists() else []:
        content = fpath.read_text(encoding="utf-8")
        date_str = fpath.stem  # 文件名即日期
        cursor.execute("""
            INSERT OR IGNORE INTO episodes (date, title, summary, file_path)
            VALUES (?, ?, ?, ?)
        """, (date_str, f"情境记忆 {date_str}", content[:500], str(fpath)))
        chroma_add("episodes", f"ep_{date_str}", content[:2000],
                   {"date": date_str, "file": str(fpath)})
        imported += 1

    conn.commit()
    print(f"[导入] 共导入 {imported} 个记忆文件到数据库")
    return imported


def seed_preferences(conn):
    """初始化偏好数据"""
    prefs = [
        ("沟通", "回复方式", "直接给结论，不要铺垫", 5),
        ("沟通", "任务交付", "一次性交付完整方案，不要分步确认", 5),
        ("沟通", "代码风格", "完整代码，不要省略号，不要'其余不变'", 5),
        ("工作习惯", "工作时间", "夜间工作，睡前交代任务，醒来看结果", 4),
        ("工作习惯", "自动化优先", "能自动化的绝不手动", 5),
        ("工作习惯", "成本敏感", "优先使用免费/低成本 API 方案", 4),
        ("技术", "后端", "Python Flask", 5),
        ("技术", "前端", "React + TypeScript + Vite", 5),
        ("技术", "数据库", "PostgreSQL（生产）+ SQLite（工具）", 4),
        ("技术", "UI风格", "深蓝科技风，数据可视化，大屏看板", 4),
    ]
    cursor = conn.cursor()
    for cat, key, val, conf in prefs:
        cursor.execute("""
            INSERT OR REPLACE INTO preferences (category, key, value, confidence)
            VALUES (?, ?, ?, ?)
        """, (cat, key, val, conf))
    conn.commit()
    print(f"[初始化] 偏好数据已写入 {len(prefs)} 条")


def seed_failures(conn):
    """初始化失败记忆"""
    failures = [
        ("F001", "西藏项目", "API 返回 500", "数据库迁移不完整", "执行 flask db upgrade", "每次改 models.py 必须迁移"),
        ("F002", "西藏项目", "前端构建报错 CATEGORIES is not defined", "重构时移除了常量但未更新引用", "重新定义常量", "重构时全局搜索所有引用"),
        ("F003", "西藏项目", "App 崩溃", "JSON.parse 无 try-catch", "包裹 try-catch", "所有 JSON.parse 必须有 try-catch"),
        ("F004", "西藏项目", "warehouseList.map 报错", "API 返回结构变更未同步前端", "使用 data?.items ?? []", "后端变更必须同步前端"),
        ("F005", "系统", "SSH 超时挂起", "frp 隧道断开", "重启 frp 客户端", "SSH 命令设置 ConnectTimeout"),
        ("F006", "系统", "pip 安装成功但 import 失败", "多 Python 版本路径问题", "用 python3 -m pip install", "Mac 上始终用 python3 -m pip"),
        ("F007", "系统", "ChromaDB 安装依赖冲突", "Python 3.9 兼容性", "安装 chromadb<0.5", "安装前检查版本兼容性"),
        ("F008", "系统", "LaunchAgent 任务不执行", "plist 使用相对路径", "改为绝对路径", "launchd plist 必须用绝对路径"),
    ]
    cursor = conn.cursor()
    for code, proj, symptom, cause, fix, lesson in failures:
        cursor.execute("""
            INSERT OR IGNORE INTO failures (code, project, symptom, root_cause, fix, lesson)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (code, proj, symptom, cause, fix, lesson))
        chroma_add("failures", code, f"{symptom} {cause} {lesson}",
                   {"code": code, "project": proj})
    conn.commit()
    print(f"[初始化] 失败记忆已写入 {len(failures)} 条")


def seed_api_keys(conn):
    """初始化 API Keys 信息（只存提示，不存明文）"""
    keys = [
        ("Groq", "gsk_****", "免费", 1),
        ("Kimi/Moonshot", "sk-****", "¥491.43", 2),
        ("智谱AI", "****", "未知", 3),
        ("OpenRouter", "sk-or-****", "无限额度", 4),
        ("OpenAI", "待配置", "待查", 5),
        ("Anthropic", "待配置", "待查", 6),
    ]
    cursor = conn.cursor()
    for provider, hint, balance, priority in keys:
        cursor.execute("""
            INSERT OR REPLACE INTO api_keys (provider, key_hint, balance, priority)
            VALUES (?, ?, ?, ?)
        """, (provider, hint, balance, priority))
    conn.commit()
    print(f"[初始化] API Keys 信息已写入 {len(keys)} 条")


# ─────────────────────────────────────────────
# 查询接口
# ─────────────────────────────────────────────
def query_memory(query_text: str, top_k: int = 5):
    """混合查询：关键词匹配 + 向量语义检索"""
    conn = get_db()
    results = []

    # 1. SQLite 关键词搜索（anchors + content）
    cursor = conn.cursor()
    like_q = f"%{query_text}%"
    rows = cursor.execute("""
        SELECT layer, module, content, confidence, anchors
        FROM core_memory
        WHERE anchors LIKE ? OR content LIKE ?
        ORDER BY confidence DESC, frequency DESC
        LIMIT ?
    """, (like_q, like_q, top_k)).fetchall()

    for row in rows:
        results.append({
            "source": "sqlite",
            "layer": row["layer"],
            "module": row["module"],
            "snippet": row["content"][:300],
            "confidence": row["confidence"],
        })

    # 2. ChromaDB 语义检索
    semantic = chroma_query("memory_files", query_text, n_results=top_k)
    for doc, meta in semantic:
        results.append({
            "source": "chromadb",
            "layer": meta.get("layer", "?"),
            "module": meta.get("file", "?"),
            "snippet": doc[:300],
            "confidence": 3,
        })

    # 3. 失败记忆检索
    failure_rows = cursor.execute("""
        SELECT code, project, symptom, lesson
        FROM failures
        WHERE symptom LIKE ? OR lesson LIKE ? OR root_cause LIKE ?
        LIMIT 3
    """, (like_q, like_q, like_q)).fetchall()
    for row in failure_rows:
        results.append({
            "source": "failures",
            "layer": "failure",
            "module": row["code"],
            "snippet": f"[{row['code']}] {row['symptom']} → {row['lesson']}",
            "confidence": 5,
        })

    conn.close()

    # 去重并格式化输出
    seen = set()
    print(f"\n=== 记忆查询: '{query_text}' ===\n")
    for r in results:
        key = r["snippet"][:100]
        if key in seen:
            continue
        seen.add(key)
        conf_stars = "★" * r["confidence"] + "☆" * (5 - r["confidence"])
        print(f"[{r['source']}] [{r['layer']}] {r['module']}")
        print(f"  置信度: {conf_stars}")
        print(f"  内容: {r['snippet'][:200]}")
        print()


def show_stats():
    """显示记忆系统统计"""
    conn = get_db()
    cursor = conn.cursor()

    print("\n=== AI 记忆系统统计 ===\n")

    tables = ["core_memory", "preferences", "failures", "episodes", "todos", "api_keys"]
    for table in tables:
        try:
            count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table:20s}: {count:4d} 条")
        except Exception:
            print(f"  {table:20s}: (表不存在)")

    # 显示待办事项
    todos = cursor.execute("""
        SELECT task, project, priority, status FROM todos
        WHERE status = 'open' ORDER BY priority LIMIT 10
    """).fetchall()
    if todos:
        print("\n--- 待办事项 (open) ---")
        for t in todos:
            print(f"  [P{t['priority']}] [{t['project']}] {t['task']}")

    # ChromaDB 状态
    client = get_chroma_client()
    if client:
        try:
            cols = client.list_collections()
            print(f"\n  ChromaDB 集合数: {len(cols)}")
            for col in cols:
                c = client.get_collection(col.name)
                print(f"    {col.name}: {c.count()} 条向量")
        except Exception as e:
            print(f"  ChromaDB: 错误 ({e})")
    else:
        print("\n  ChromaDB: 未安装（降级为纯 SQLite 模式）")

    conn.close()


def add_todo(task: str, project: str = "", priority: int = 3):
    conn = get_db()
    conn.execute("""
        INSERT INTO todos (task, project, priority) VALUES (?, ?, ?)
    """, (task, project, priority))
    conn.commit()
    conn.close()
    print(f"[待办] 已添加: {task}")


# ─────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="AI 记忆查询系统")
    parser.add_argument("--init",        action="store_true", help="初始化数据库并导入所有记忆")
    parser.add_argument("--query", "-q", type=str,            help="语义查询记忆")
    parser.add_argument("--stats",       action="store_true", help="显示记忆统计")
    parser.add_argument("--add-todo",    type=str,            help="添加待办事项")
    parser.add_argument("--project",     type=str, default="", help="项目名（配合 --add-todo）")
    parser.add_argument("--priority",    type=int, default=3,  help="优先级 1-5（配合 --add-todo）")
    args = parser.parse_args()

    if args.init:
        print("[初始化] 开始建立记忆数据库...")
        conn = get_db()
        import_markdown_to_db(conn)
        seed_preferences(conn)
        seed_failures(conn)
        seed_api_keys(conn)
        conn.close()
        show_stats()
        print("\n[完成] 记忆数据库初始化完毕！")

    elif args.query:
        query_memory(args.query)

    elif args.stats:
        show_stats()

    elif args.add_todo:
        add_todo(args.add_todo, args.project, args.priority)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
