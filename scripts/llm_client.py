#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TCZ · 统一 LLM 调用工具库 llm_client.py
- 降级顺序：Gemini(本地代理) → Kimi → OpenRouter(Groq/Claude)
- 每个模型有独立超时（threading.Timer 强制中断，不会永久卡死）
- 失败自动写入日志，不影响主流程

用法：
  from llm_client import call_llm, call_llm_json
  result = call_llm(prompt)          # 返回字符串，失败返回 None
  data   = call_llm_json(prompt)     # 返回 dict，失败返回 None
"""

import json
import os
import sys
import threading
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# ============================================================
# 配置
# ============================================================
MEMORY_ROOT = Path.home() / "ai_memory"
LOG_PATH = MEMORY_ROOT / "logs" / "llm_client.log"

DEEPSEEK_KEY = os.environ.get("DEEPSEEK_KEY", "YOUR_DEEPSEEK_KEY_HERE")
GLM_KEY = os.environ.get("GLM_KEY", "YOUR_GLM_KEY_HERE")
GROQ_KEY = os.environ.get("GROQ_KEY", "YOUR_GROQ_KEY_HERE")
KIMI_KEY = os.environ.get("KIMI_KEY", "YOUR_KIMI_KEY_HERE")
GEMINI_PROXY = "http://127.0.0.1:11435"

# 降级链：Gemini(本地免费) → Kimi(付费稳定) → OpenRouter(兜底)
PROVIDERS = [
    {
        "name": "Gemini-2.5-Flash",
        "url": f"{GEMINI_PROXY}/v1/chat/completions",
        "model": "gemini-2.5-flash",
        "key": "vertex-ai-proxy",
        "timeout": 20,
        "max_tokens": 800,
    },
    {
        "name": "DeepSeek-V3",
        "url": "https://api.deepseek.com/v1/chat/completions",
        "model": "deepseek-chat",
        "key": DEEPSEEK_KEY,
        "timeout": 25,
        "max_tokens": 1000,
    },
    {
        "name": "GLM-4-Flash",
        "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "model": "glm-4-flash",
        "key": GLM_KEY,
        "timeout": 20,
        "max_tokens": 1000,
    },
    {
        "name": "Kimi",
        "url": "https://api.moonshot.cn/v1/chat/completions",
        "model": "moonshot-v1-8k",
        "key": KIMI_KEY,
        "timeout": 20,
        "max_tokens": 800,
    },
    {
        "name": "Groq-Llama3",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.1-8b-instant",
        "key": GROQ_KEY,
        "timeout": 15,
        "max_tokens": 800,
    },
    {
        "name": "OpenRouter-Claude",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "anthropic/claude-3-haiku",
        "key": os.environ.get("OPENROUTER_API_KEY", ""),
        "timeout": 20,
        "max_tokens": 800,
    },
]


# ============================================================
# 工具函数
# ============================================================
def _log(msg: str):
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def _call_single(provider: dict, prompt: str) -> str:
    """调用单个 provider，带 threading 强制超时。成功返回文本，失败抛异常。"""
    api_key = provider.get("key", "")
    if not api_key:
        raise ValueError(f"No API key for {provider['name']}")

    data = json.dumps({
        "model": provider["model"],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": provider["max_tokens"],
        "temperature": 0.3,
        "stream": False,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    # OpenRouter 需要额外 header
    if "openrouter" in provider["url"]:
        headers["HTTP-Referer"] = "https://localhost"
        headers["X-Title"] = "TCZ-AI-Memory"

    req = urllib.request.Request(provider["url"], data=data, headers=headers)

    result_holder = [None]
    error_holder = [None]

    def do_request():
        try:
            with urllib.request.urlopen(req, timeout=provider["timeout"]) as resp:
                raw = json.loads(resp.read())
                result_holder[0] = raw["choices"][0]["message"]["content"].strip()
        except Exception as e:
            error_holder[0] = e

    # threading 强制超时（socket timeout 之外的最终保障）
    t = threading.Thread(target=do_request, daemon=True)
    t.start()
    t.join(timeout=provider["timeout"] + 5)

    if t.is_alive():
        raise TimeoutError(f"{provider['name']} 超时（>{provider['timeout']+5}s）")
    if error_holder[0]:
        raise error_holder[0]
    if result_holder[0] is None:
        raise ValueError(f"{provider['name']} 返回空结果")

    return result_holder[0]


def _clean_json(text: str) -> str:
    """从 LLM 响应中提取干净的 JSON 字符串"""
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            cleaned = part.replace("json", "", 1).strip()
            if cleaned.startswith("{") or cleaned.startswith("["):
                text = cleaned
                break
    text = text.strip()
    # 补全被截断的 JSON
    open_count = text.count("{") - text.count("}")
    if open_count > 0:
        text = text.rstrip(", \n") + "}" * open_count
    return text


# ============================================================
# 主接口
# ============================================================
def call_llm(prompt: str, expect_json: bool = False):
    """
    按降级链调用 LLM（Gemini → Kimi → OpenRouter）。
    返回响应文本字符串，全部失败返回 None。
    """
    for provider in PROVIDERS:
        name = provider["name"]
        # 跳过没有 key 的 provider
        if not provider.get("key"):
            continue
        try:
            _log(f"尝试 {name}...")
            text = _call_single(provider, prompt)

            if expect_json:
                text = _clean_json(text)
                json.loads(text)  # 验证可解析

            _log(f"✅ {name} 成功")
            return text

        except json.JSONDecodeError as e:
            _log(f"⚠️  {name} JSON解析失败: {e}，降级")
        except TimeoutError as e:
            _log(f"⏰ {name} 超时: {e}，降级")
        except Exception as e:
            _log(f"❌ {name} 失败: {type(e).__name__}: {e}，降级")

    _log("💀 所有模型均失败")
    return None


def call_llm_json(prompt: str):
    """调用 LLM 并解析为 JSON dict，失败返回 None。"""
    text = call_llm(prompt, expect_json=True)
    if text is None:
        return None
    try:
        return json.loads(text)
    except Exception as e:
        _log(f"最终 JSON 解析失败: {e}")
        return None


# ============================================================
# 命令行测试
# ============================================================
if __name__ == "__main__":
    print("=== TCZ LLM Client 测试 ===")
    print("降级顺序: Gemini → Kimi → OpenRouter\n")
    test = '只返回这个JSON，不要其他文字：{"status":"ok","model":"你的模型名"}'
    result = call_llm(test, expect_json=True)
    if result:
        print(f"✅ 成功: {result}")
    else:
        print("❌ 所有模型均失败")
