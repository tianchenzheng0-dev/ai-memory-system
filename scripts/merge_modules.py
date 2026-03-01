#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TCZ · 记忆模块自动合并器 merge_modules.py
每次蒸馏结束后自动运行，扫描所有模块文件，
找出内容高度相似的模块，用 AI 判断是否合并，
自动执行合并并更新 schema.json。

用法：
  python3 ~/ai_memory/merge_modules.py
  python3 ~/ai_memory/merge_modules.py --dry-run   # 只检测不合并
"""

import json
import sys
import os
import argparse
from pathlib import Path
from datetime import datetime

MEMORY_ROOT = Path.home() / "ai_memory"
SCHEMA_PATH = MEMORY_ROOT / "schema.json"
MODULES_DIR = MEMORY_ROOT / "modules"
LOG_PATH = MEMORY_ROOT / "logs" / "merge.log"

# 导入统一 LLM 客户端
sys.path.insert(0, str(MEMORY_ROOT))
try:
    from llm_client import call_llm_json, call_llm_text
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

# ── 工具函数 ──────────────────────────────────────────────

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [merge] {msg}"
    print(line, flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def load_schema():
    if SCHEMA_PATH.exists():
        return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return {}

def save_schema(schema):
    SCHEMA_PATH.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def get_all_module_files():
    """获取所有模块文件（modules/ 下的 .md 文件 + 根目录特定文件）"""
    files = {}
    # modules/ 目录下的所有 .md 文件
    if MODULES_DIR.exists():
        for f in MODULES_DIR.glob("*.md"):
            if f.name not in ("passwords.md", "api_providers.md"):  # 跳过敏感文件
                content = f.read_text(encoding="utf-8", errors="ignore").strip()
                if len(content) > 50:  # 忽略空文件
                    files[str(f)] = content
    # 根目录的项目文件
    for name in ["preferences.md", "failures.md", "graph.md"]:
        p = MEMORY_ROOT / name
        if p.exists():
            content = p.read_text(encoding="utf-8", errors="ignore").strip()
            if len(content) > 50:
                files[str(p)] = content
    return files

def truncate(text, max_chars=800):
    """截取文本前N字符用于相似度判断"""
    return text[:max_chars] + "..." if len(text) > max_chars else text

# ── 核心逻辑 ──────────────────────────────────────────────

def find_similar_pairs(files: dict) -> list:
    """
    用 AI 扫描所有模块，找出内容高度相似的模块对。
    返回：[{"file_a": path, "file_b": path, "reason": str, "similarity": 0-100}, ...]
    """
    if not LLM_AVAILABLE:
        log("⚠️  LLM 不可用，跳过相似度检测")
        return []

    file_list = list(files.items())
    if len(file_list) < 2:
        log("模块数量不足 2 个，无需检测")
        return []

    # 构建模块摘要列表
    summaries = []
    for path, content in file_list:
        name = Path(path).stem
        summaries.append(f"【{name}】\n{truncate(content, 600)}")

    modules_text = "\n\n---\n\n".join(summaries)

    prompt = f"""你是一个AI记忆系统的模块管理员。请分析以下记忆模块的内容，找出主题高度重叠、应该合并的模块对。

判断标准：
- 相似度 >= 80：强烈建议合并（主题几乎相同）
- 相似度 60-79：建议合并（主题有较大重叠）
- 相似度 < 60：不需要合并

以下是所有模块的内容摘要：

{modules_text}

请以JSON数组格式输出需要合并的模块对（只输出相似度>=60的）：
[
  {{
    "module_a": "模块名（不含.md）",
    "module_b": "模块名（不含.md）",
    "similarity": 85,
    "reason": "两个模块都在记录西藏项目的物流信息，主题高度重叠",
    "suggested_name": "合并后建议使用的模块名",
    "merge_strategy": "以module_a为主体，将module_b内容追加合并"
  }}
]

如果没有需要合并的模块，返回空数组 []。只输出JSON，不要任何其他内容。"""

    try:
        result = call_llm_json(prompt)
        if isinstance(result, list):
            log(f"AI 检测到 {len(result)} 对相似模块")
            return result
        else:
            log("AI 返回格式异常，跳过合并")
            return []
    except Exception as e:
        log(f"AI 调用失败：{e}")
        return []

def merge_two_modules(path_a: str, path_b: str, suggested_name: str,
                      merge_strategy: str, reason: str, dry_run: bool) -> bool:
    """
    将两个模块合并为一个。
    - 以 path_a 为主体，将 path_b 内容追加
    - 删除 path_b
    - 如果 suggested_name 与 path_a 不同，重命名 path_a
    - 更新 schema.json
    """
    pa = Path(path_a)
    pb = Path(path_b)

    if not pa.exists() or not pb.exists():
        log(f"⚠️  文件不存在，跳过：{path_a} 或 {path_b}")
        return False

    content_a = pa.read_text(encoding="utf-8", errors="ignore")
    content_b = pb.read_text(encoding="utf-8", errors="ignore")

    if dry_run:
        log(f"[DRY-RUN] 将合并：{pa.name} + {pb.name} → {suggested_name}.md")
        log(f"  原因：{reason}")
        return True

    # 用 AI 生成合并后的内容
    if LLM_AVAILABLE:
        merge_prompt = f"""请将以下两个记忆模块合并为一个，去除重复内容，保留所有有价值的信息，按时间或主题组织。

模块A（{pa.stem}）：
{content_a}

模块B（{pb.stem}）：
{content_b}

合并策略：{merge_strategy}

请直接输出合并后的Markdown内容，不要任何额外说明。"""
        try:
            merged_content = call_llm_text(merge_prompt)
        except Exception as e:
            log(f"AI 合并内容生成失败：{e}，使用简单拼接")
            merged_content = content_a + f"\n\n---\n<!-- 合并自 {pb.stem} ({datetime.now().strftime('%Y-%m-%d')}) -->\n\n" + content_b
    else:
        merged_content = content_a + f"\n\n---\n<!-- 合并自 {pb.stem} ({datetime.now().strftime('%Y-%m-%d')}) -->\n\n" + content_b

    # 备份原文件
    backup_dir = MEMORY_ROOT / ".backup"
    backup_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    (backup_dir / f"{pa.stem}_before_merge_{ts}.md").write_text(content_a, encoding="utf-8")
    (backup_dir / f"{pb.stem}_before_merge_{ts}.md").write_text(content_b, encoding="utf-8")

    # 确定最终路径
    final_name = suggested_name if suggested_name else pa.stem
    final_path = pa.parent / f"{final_name}.md"

    # 写入合并内容
    final_path.write_text(merged_content, encoding="utf-8")

    # 如果重命名了，删除旧的 path_a
    if final_path != pa:
        pa.unlink()

    # 删除 path_b
    pb.unlink()

    # 更新 schema.json
    schema = load_schema()
    modules = schema.get("modules", {})
    # 删除旧条目
    for key in [pa.stem, pb.stem]:
        modules.pop(key, None)
    # 添加新条目
    modules[final_name] = {
        "file": f"modules/{final_name}.md",
        "description": f"由 {pa.stem} 和 {pb.stem} 合并而来（{reason[:50]}）",
        "merged_from": [pa.stem, pb.stem],
        "merged_at": datetime.now().strftime("%Y-%m-%d")
    }
    schema["modules"] = modules
    save_schema(schema)

    log(f"✅ 合并完成：{pa.stem} + {pb.stem} → {final_name}.md")
    log(f"  原因：{reason}")
    return True

# ── 主流程 ────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="记忆模块自动合并器")
    parser.add_argument("--dry-run", action="store_true", help="只检测不执行合并")
    parser.add_argument("--min-similarity", type=int, default=75,
                        help="最低相似度阈值（默认75）")
    args = parser.parse_args()

    log("========== 开始模块相似度检测 ==========")

    files = get_all_module_files()
    log(f"共扫描到 {len(files)} 个模块文件")

    if len(files) < 2:
        log("模块数量不足，无需合并检测")
        return

    # 找出相似对
    similar_pairs = find_similar_pairs(files)

    # 过滤低于阈值的
    to_merge = [p for p in similar_pairs if p.get("similarity", 0) >= args.min_similarity]

    if not to_merge:
        log("✅ 未发现需要合并的模块，记忆结构健康")
        return

    log(f"发现 {len(to_merge)} 对需要合并的模块")

    # 构建文件名到路径的映射
    name_to_path = {}
    for path in files.keys():
        name_to_path[Path(path).stem] = path

    merged_count = 0
    skip_count = 0

    for pair in to_merge:
        module_a = pair.get("module_a", "")
        module_b = pair.get("module_b", "")
        similarity = pair.get("similarity", 0)
        reason = pair.get("reason", "")
        suggested_name = pair.get("suggested_name", module_a)
        merge_strategy = pair.get("merge_strategy", "")

        path_a = name_to_path.get(module_a)
        path_b = name_to_path.get(module_b)

        if not path_a or not path_b:
            log(f"⚠️  找不到模块文件：{module_a} 或 {module_b}，跳过")
            skip_count += 1
            continue

        log(f"处理：{module_a} + {module_b}（相似度 {similarity}%）")

        success = merge_two_modules(
            path_a, path_b, suggested_name,
            merge_strategy, reason, args.dry_run
        )

        if success:
            merged_count += 1
            # 更新映射，防止后续对引用已删除的文件
            if not args.dry_run:
                name_to_path.pop(module_b, None)
                if suggested_name != module_a:
                    name_to_path.pop(module_a, None)
                    new_path = str(MODULES_DIR / f"{suggested_name}.md")
                    name_to_path[suggested_name] = new_path
        else:
            skip_count += 1

    if args.dry_run:
        log(f"[DRY-RUN] 检测完成：{merged_count} 对可合并，{skip_count} 对跳过")
    else:
        log(f"========== 合并完成：{merged_count} 对已合并，{skip_count} 对跳过 ==========")

if __name__ == "__main__":
    main()
