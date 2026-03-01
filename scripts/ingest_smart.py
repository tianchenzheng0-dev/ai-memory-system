#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TCZ · 智能信息摄入处理器 ingest_smart.py v2
- 使用 llm_client.py 统一调用（自动降级 Kimi→Gemini→Groq）
- 每个模型独立超时，全链路不卡死
- 自动识别新类型，动态新建模块

用法：
  python3 ~/ai_memory/ingest_smart.py "内容" "来源"
  echo "内容" | python3 ~/ai_memory/ingest_smart.py - "来源"
"""

import json
import sys
from pathlib import Path
from datetime import datetime

MEMORY_ROOT = Path.home() / "ai_memory"
SCHEMA_PATH = MEMORY_ROOT / "schema.json"

# 导入统一 LLM 客户端
sys.path.insert(0, str(MEMORY_ROOT))
try:
    from llm_client import call_llm_json, _log
    try:
        from memory_lock import MemoryLock, safe_append
        LOCK_AVAILABLE = True
    except ImportError:
        LOCK_AVAILABLE = False
        import contextlib
        @contextlib.contextmanager
        def MemoryLock(name="default", timeout=30):
            yield
        def safe_append(path, content, lock_name=None):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)
            return True
except ImportError:
    def call_llm_json(prompt): return None
    def _log(msg): pass
    LOCK_AVAILABLE = False
    import contextlib
    @contextlib.contextmanager
    def MemoryLock(name="default", timeout=30):
        yield
    def safe_append(path, content, lock_name=None):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(content)
        return True


def load_schema():
    if SCHEMA_PATH.exists():
        return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return {"modules": {}, "layers": {}}


def save_schema(schema):
    SCHEMA_PATH.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")


def keyword_fallback(content: str, schema: dict) -> dict:
    """关键词降级分类（LLM全部失败时使用）"""
    kw_map = [
        (["股", "买入", "卖出", "涨", "跌", "仓位", "止损", "A股", "美股", "港股",
          "期货", "基金", "ETF", "复盘", "持仓", "北向", "南向", "板块"], "trading"),
        (["西藏", "碳汇", "林草", "tibet", "可视化大屏"], "tibet"),
        (["船行", "航运", "ship"], "ship"),
        (["HFT", "高频", "量化", "策略"], "hft"),
        (["规范", "原则", "TDD", "测试", "代码", "架构", "备份", "部署",
          "迁移", "必须先", "禁止", "一定要"], "work_norms"),
    ]
    for keywords, module in kw_map:
        if any(kw in content for kw in keywords):
            return {"module": module, "summary": content[:15], "tags": [],
                    "confidence": 2, "reason": "关键词降级", "section": "", "layer": "module"}
    return {"module": "insights", "summary": content[:15], "tags": [],
            "confidence": 1, "reason": "默认归入洞察", "section": "人生与思维", "layer": "module"}


def analyze(content: str, schema: dict) -> dict:
    """调用 LLM 分析内容，返回分类决策"""
    modules_desc = "\n".join([
        f"- {name}: {info['description']}"
        for name, info in schema.get("modules", {}).items()
    ])

    prompt = f"""将以下内容分类到TCZ记忆系统的最合适模块。

现有模块：
{modules_desc}

内容：{content[:600]}

规则：
1. 优先匹配现有模块
2. 完全不匹配时 module 填 "new"，同时填 new_module_name(英文小写) 和 new_module_description(中文)
3. summary 限15字

只返回JSON：
{{"module":"模块名","summary":"摘要","tags":["标签"],"confidence":4,"reason":"理由","section":"子分类","layer":"module","new_module_name":"","new_module_description":""}}"""

    result = call_llm_json(prompt)
    if result:
        return result

    # LLM 全部失败，关键词降级
    print("⚠️  LLM全部失败，使用关键词降级", flush=True)
    return keyword_fallback(content, schema)


def ensure_module(module_name: str, decision: dict, schema: dict):
    """确保模块存在，不存在则自动创建"""
    if module_name in schema.get("modules", {}):
        return

    desc = decision.get("new_module_description") or module_name
    keywords = decision.get("new_module_keywords") or []
    now = datetime.now().strftime("%Y-%m-%d")

    # 创建模块文件
    module_file = MEMORY_ROOT / module_name / f"{module_name}.md"
    module_file.parent.mkdir(parents=True, exist_ok=True)
    module_file.write_text(
        f"---\nmodule: {module_name}\ncreated: {now}\ndescription: {desc}\nauto_created: true\n---\n\n"
        f"# TCZ · {desc}\n\n> 由AI自动创建于 {now}\n\n## 内容记录\n\n",
        encoding="utf-8"
    )

    # 注册到 schema
    schema.setdefault("modules", {})[module_name] = {
        "description": desc,
        "path": f"{module_name}/{module_name}.md",
        "layer": "module",
        "created": now,
        "keywords": keywords,
        "sections": ["内容记录"],
        "auto_created": True
    }
    save_schema(schema)
    print(f"🆕 新模块已创建: {module_name} ({desc})", flush=True)
    _log(f"新模块已创建: {module_name} ({desc})")


def write_entry(content: str, decision: dict, schema: dict, source: str) -> Path:
    """写入记忆文件"""
    module = decision.get("module", "insights")
    if module == "new":
        module = decision.get("new_module_name") or "misc"
        decision["module"] = module

    ensure_module(module, decision, schema)

    # 确定文件路径
    if module == "work_norms":
        filepath = MEMORY_ROOT / "core2.md"
    else:
        module_info = schema.get("modules", {}).get(module, {})
        rel_path = module_info.get("path", f"{module}/{module}.md").split("（")[0].strip()
        filepath = MEMORY_ROOT / rel_path

    filepath.parent.mkdir(parents=True, exist_ok=True)

    # 构建条目
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    summary = decision.get("summary") or content[:15]
    tags_str = " ".join([f"`{t}`" for t in decision.get("tags", [])])
    section = decision.get("section", "")

    entry = f"\n### [{ts}] {summary}\n> 来源：{source} | {tags_str}\n\n{content}\n"

    # 尝试插入到对应章节
    if filepath.exists() and section:
        existing = filepath.read_text(encoding="utf-8")
        header = f"## {section}"
        if header in existing:
            insert_at = existing.find(header) + len(header)
            next_sec = existing.find("\n## ", insert_at)
            if next_sec == -1:
                existing += entry
            else:
                existing = existing[:next_sec] + entry + existing[next_sec:]
            filepath.write_text(existing, encoding="utf-8")
            return filepath

    # 直接追加（带锁保护，防止多AI并发写入）
    lock_name = f"write_{filepath.stem}"
    if LOCK_AVAILABLE:
        safe_append(str(filepath), entry, lock_name)
    else:
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(entry)
    return filepath


def process(content: str, source: str = "manual"):
    """主处理流程"""
    print(f"\n{'='*50}", flush=True)
    print(f"📥 处理: {content[:50]}...", flush=True)
    print(f"{'='*50}", flush=True)

    schema = load_schema()

    print("🤖 AI分析中（Kimi→Gemini→Groq→关键词）...", flush=True)
    decision = analyze(content, schema)

    module = decision.get("module", "insights")
    if module == "new":
        module = decision.get("new_module_name") or "misc"

    print(f"📂 分类: {module}", flush=True)
    print(f"📌 摘要: {decision.get('summary', '')}", flush=True)
    print(f"🏷️  标签: {', '.join(decision.get('tags', []))}", flush=True)
    print(f"💡 理由: {decision.get('reason', '')}", flush=True)

    # 重新加载 schema（ensure_module 可能修改了它）
    schema = load_schema()
    filepath = write_entry(content, decision, schema, source)
    print(f"✅ 已写入: {filepath}", flush=True)

    # 今日缓冲（带锁保护）
    ts = datetime.now().strftime("%H:%M")
    today_entry = f"\n**[{ts} 摄入·{module}]** {source} | {decision.get('summary', '')}\n"
    if LOCK_AVAILABLE:
        safe_append(str(MEMORY_ROOT / "today.md"), today_entry, "today_md")
    else:
        with open(MEMORY_ROOT / "today.md", "a", encoding="utf-8") as f:
            f.write(today_entry)
    print("📌 今日缓冲已同步", flush=True)

    return decision


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "-":
        content = sys.stdin.read().strip()
        source = sys.argv[2] if len(sys.argv) > 2 else "stdin"
    elif len(sys.argv) >= 2:
        content = sys.argv[1]
        source = sys.argv[2] if len(sys.argv) > 2 else "manual"
    else:
        print("=== TCZ · 智能信息摄入 ===")
        print("输入内容（两次回车确认）：\n")
        lines = []
        try:
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
        except (KeyboardInterrupt, EOFError):
            pass
        content = "\n".join(lines).strip()
        source = input("\n来源（回车跳过）: ").strip() or "manual"

    if not content:
        print("❌ 内容为空")
        return

    process(content, source)


if __name__ == "__main__":
    main()
