#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TCZ · 蒸馏 LLM 调用器 distill_llm.py
供 distill.sh 调用，处理所有 API 降级逻辑。

用法：
  python3 ~/ai_memory/distill_llm.py <prompt_file>

成功：输出 JSON 字符串到 stdout，退出码 0
失败：输出错误到 stderr，退出码 1
"""

import json
import os
import sys
import threading
import urllib.request
from pathlib import Path
from datetime import datetime

MEMORY_ROOT = Path.home() / "ai_memory"
LOG_PATH = MEMORY_ROOT / "logs" / "distill.log"

KIMI_KEY = "sk-w80lJYxOgqz3QCVuc62WqHCmaDUzqDfaCEttahi3xQJyz1IV"
GEMINI_PROXY = "http://127.0.0.1:11435"


def log(msg):
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [distill_llm] {msg}\n")
        print(f"[distill_llm] {msg}", file=sys.stderr, flush=True)
    except Exception:
        pass


def call_with_timeout(url, api_key, model, prompt, max_tokens=2000, timeout=20, extra_headers=None):
    """带 threading 超时保护的 LLM 调用，返回文本或抛异常"""
    data = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "stream": False,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if extra_headers:
        headers.update(extra_headers)

    req = urllib.request.Request(url, data=data, headers=headers)

    result_holder = [None]
    error_holder = [None]

    def do_request():
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = json.loads(resp.read())
                result_holder[0] = raw["choices"][0]["message"]["content"].strip()
        except Exception as e:
            error_holder[0] = e

    t = threading.Thread(target=do_request, daemon=True)
    t.start()
    t.join(timeout=timeout + 5)  # 额外5秒作为最终保障

    if t.is_alive():
        raise TimeoutError(f"超时（>{timeout+5}s）")
    if error_holder[0]:
        raise error_holder[0]
    if result_holder[0] is None:
        raise ValueError("返回空结果")

    return result_holder[0]


def clean_json(text):
    """从 LLM 响应中提取干净的 JSON"""
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            cleaned = part.replace("json", "", 1).strip()
            if cleaned.startswith("{"):
                text = cleaned
                break
    text = text.strip()
    # 补全被截断的 JSON
    open_count = text.count("{") - text.count("}")
    if open_count > 0:
        text = text.rstrip(", \n") + "}" * open_count
    return text


def try_call(name, url, key, model, prompt, extra_headers=None):
    """尝试调用一个模型，返回 (success, json_text)"""
    if not key:
        log(f"跳过 {name}（无 API Key）")
        return False, None
    try:
        log(f"尝试 {name}...")
        text = call_with_timeout(url, key, model, prompt, extra_headers=extra_headers)
        text = clean_json(text)
        json.loads(text)  # 验证 JSON 有效
        log(f"✅ {name} 成功")
        return True, text
    except json.JSONDecodeError as e:
        log(f"⚠️  {name} JSON解析失败: {e}")
        return False, None
    except TimeoutError as e:
        log(f"⏰ {name} 超时: {e}")
        return False, None
    except Exception as e:
        log(f"❌ {name} 失败: {type(e).__name__}: {e}")
        return False, None


def main():
    if len(sys.argv) < 2:
        print("用法: python3 distill_llm.py <prompt_file>", file=sys.stderr)
        sys.exit(1)

    prompt_file = Path(sys.argv[1])
    if not prompt_file.exists():
        print(f"Prompt 文件不存在: {prompt_file}", file=sys.stderr)
        sys.exit(1)

    prompt = prompt_file.read_text(encoding="utf-8").strip()
    if not prompt:
        print("Prompt 文件为空", file=sys.stderr)
        sys.exit(1)

    # ============================================================
    # 降级链：Gemini(Vertex AI) → Kimi → OpenRouter(Groq → Claude)
    # ============================================================

    # 1. Gemini 2.5 Flash（通过本地代理）
    ok, result = try_call(
        "Gemini-2.5-Flash",
        f"{GEMINI_PROXY}/v1/chat/completions",
        "vertex-ai-proxy",
        "gemini-2.5-flash",
        prompt,
    )
    if ok:
        print(result)
        return

    # 2. Kimi
    ok, result = try_call(
        "Kimi",
        "https://api.moonshot.cn/v1/chat/completions",
        KIMI_KEY,
        "moonshot-v1-8k",
        prompt,
    )
    if ok:
        print(result)
        return

    # 3. OpenRouter - Groq/Llama3（免费）
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    ok, result = try_call(
        "Groq/Llama3",
        "https://openrouter.ai/api/v1/chat/completions",
        openrouter_key,
        "meta-llama/llama-3.1-8b-instruct:free",
        prompt,
        extra_headers={"HTTP-Referer": "https://localhost", "X-Title": "TCZ-Memory"},
    )
    if ok:
        print(result)
        return

    # 4. OpenRouter - Claude Haiku
    ok, result = try_call(
        "Claude Haiku",
        "https://openrouter.ai/api/v1/chat/completions",
        openrouter_key,
        "anthropic/claude-3-haiku",
        prompt,
        extra_headers={"HTTP-Referer": "https://localhost", "X-Title": "TCZ-Memory"},
    )
    if ok:
        print(result)
        return

    # 全部失败
    log("💀 所有模型均失败")
    sys.exit(1)


if __name__ == "__main__":
    main()
