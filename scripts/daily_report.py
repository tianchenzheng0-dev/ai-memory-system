#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 记忆系统 - 每日状态邮件
每天 09:00 自动发送到 164204@qq.com
"""

import os
import sys
import json
import sqlite3
import smtplib
import subprocess
from pathlib import Path
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.header import Header
from email import encoders

# ─────────────────────────────────────────────
# 配置（SMTP密码从环境变量或配置文件读取）
# ─────────────────────────────────────────────
MEMORY_ROOT = Path.home() / "ai_memory"
CONFIG_FILE = MEMORY_ROOT / "modules" / "email_config.json"

TO_EMAIL    = "164204@qq.com"
FROM_EMAIL  = ""   # 从配置文件读取
SMTP_PASS   = ""   # QQ邮箱授权码（非登录密码）
SMTP_HOST   = "smtp.qq.com"
SMTP_PORT   = 587

def load_config():
    """从配置文件加载邮件配置"""
    global FROM_EMAIL, SMTP_PASS
    if CONFIG_FILE.exists():
        cfg = json.loads(CONFIG_FILE.read_text())
        FROM_EMAIL = cfg.get("from_email", "")
        SMTP_PASS  = cfg.get("smtp_pass", "")
        return bool(FROM_EMAIL and SMTP_PASS)
    return False

# ─────────────────────────────────────────────
# 数据收集
# ─────────────────────────────────────────────
def get_db_stats():
    """从SQLite获取记忆系统统计"""
    db_path = MEMORY_ROOT / "db" / "memory.db"
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        stats = {}
        for table in ["core_memory", "preferences", "failures", "episodes", "todos", "api_keys"]:
            try:
                stats[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except:
                stats[table] = 0
        # 获取待办
        todos = conn.execute("""
            SELECT task, project, priority FROM todos
            WHERE status='open' ORDER BY priority LIMIT 10
        """).fetchall()
        stats["open_todos"] = [dict(t) for t in todos]
        # 获取API Keys状态
        api_keys = conn.execute("""
            SELECT provider, balance, priority FROM api_keys ORDER BY priority
        """).fetchall()
        stats["api_keys_list"] = [dict(k) for k in api_keys]
        conn.close()
        return stats
    except Exception as e:
        return {"error": str(e)}

def get_api_balances():
    """尝试读取API余额信息"""
    balances = {}
    # 从 passwords.md 中提取余额信息（简单grep）
    pw_file = MEMORY_ROOT / "modules" / "passwords.md"
    if pw_file.exists():
        content = pw_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            if "余额" in line or "balance" in line.lower():
                balances["raw"] = balances.get("raw", "") + line.strip() + "\n"
    return balances

def get_today_buffer():
    """获取今日缓冲区内容摘要"""
    today_file = MEMORY_ROOT / "today.md"
    if not today_file.exists():
        return "（今日缓冲区为空）"
    content = today_file.read_text(encoding="utf-8")
    lines = [l for l in content.splitlines() if l.strip() and not l.startswith("---")]
    # 只取最后20行
    return "\n".join(lines[-20:]) if lines else "（无内容）"

def get_system_status():
    """获取Mac系统状态"""
    status = {}
    try:
        # 磁盘空间
        result = subprocess.run(["df", "-h", str(Path.home())],
                                capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 5:
                status["disk_used"]  = parts[2]
                status["disk_avail"] = parts[3]
                status["disk_pct"]   = parts[4]
                break
    except:
        status["disk"] = "获取失败"
    try:
        # 内存
        result = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5)
        status["memory_raw"] = result.stdout[:200]
    except:
        pass
    return status


# ─────────────────────────────────────────────
# AI 实时生成每日正能量夸赞语
# ─────────────────────────────────────────────
def _gen_daily_praise(stats=None):
    """调用 LLM 实时生成每日专属正能量鼓励，失败则返回备用文案"""
    try:
        sys.path.insert(0, str(MEMORY_ROOT))
        from llm_client import call_llm

        # 构建上下文提示
        context_parts = []
        if stats:
            todos = stats.get("open_todos", [])
            if todos:
                todo_names = "、".join(t.get("task", "") for t in todos[:3])
                context_parts.append(f"当前待办：{todo_names}")
            mem_count = stats.get("total_memories", 0)
            if mem_count:
                context_parts.append(f"记忆库已积累 {mem_count} 条")
        context = "；".join(context_parts) if context_parts else ""

        today = datetime.now().strftime("%Y年%m月%d日")
        prompt = f"""今天是 {today}。你是一个了解用户的 AI 助手，需要给用户 TCZ 写一段今日专属正能量鼓励。

用户背景：TCZ 是一个独立开发者，同时在推进西藏农产品项目（Flask+React全栈）、AI 记忆系统（v3.0，六层架构+SQLite+ChromaDB）、量化交易（HFT研究），还在学习 AI 工具链。他偶尔懒，但执行力强，喜欢把事情系统化。
{f"今日信息：{context}" if context else ""}

要求：
- 50-80字，口语化，真诚不浮夸
- 结合他实际在做的事情，说得具体一点
- 每次都要不一样，不要用模板化的句子
- 不要用"你好"开头，直接说正题
- 不要用感叹号结尾，平静有力量

只输出鼓励的话，不要任何前缀或解释。"""

        result = call_llm(prompt)
        if result and len(result.strip()) > 10:
            return result.strip()
    except Exception as e:
        pass

    # 备用文案（LLM 不可用时）
    import hashlib
    backups = [
        "你在做的事情，比大多数人想象的要难。但你还是在做，而且做得很扎实。",
        "西藏项目、记忆系统、量化研究——你一个人扛着这些，不容易。今天也继续。",
        "你把 AI 用成了自己的基础设施，这种思维方式，时间会证明它的价值。",
        "稳定推进本身就是一种了不起的能力。你今天也做到了。",
        "你不是在等机会，你在一件一件地创造条件。这个区别，很重要。",
    ]
    idx = int(hashlib.md5(str(datetime.now().date()).encode()).hexdigest(), 16) % len(backups)
    return backups[idx]


# ─────────────────────────────────────────────
# 邮件内容生成
# ─────────────────────────────────────────────
def build_html_email(stats, balances, today_buf, sys_status):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── 每日正能量夸赞语（AI 实时生成，每天不同）──
    daily_praise = _gen_daily_praise(stats)


    # 待办列表
    todos_html = ""
    if stats.get("open_todos"):
        for t in stats["open_todos"]:
            priority_color = {1: "#e74c3c", 2: "#e67e22", 3: "#3498db", 4: "#27ae60", 5: "#95a5a6"}
            color = priority_color.get(t.get("priority", 3), "#3498db")
            todos_html += f'<li><span style="color:{color};font-weight:bold">[P{t["priority"]}]</span> {t["task"]} <small style="color:#888">({t["project"]})</small></li>'
    else:
        todos_html = "<li>暂无待办事项</li>"

    # API Keys 状态
    api_html = ""
    if stats.get("api_keys_list"):
        for k in stats["api_keys_list"]:
            balance = k.get("balance", "未知")
            # 标记需要充值的
            needs_attention = any(w in str(balance) for w in ["待配置", "待查", "0", "不足"])
            icon = "⚠️" if needs_attention else "✅"
            api_html += f'<tr><td>{icon} {k["provider"]}</td><td style="color:{"#e74c3c" if needs_attention else "#27ae60"}">{balance}</td></tr>'
    else:
        api_html = '<tr><td colspan="2">无数据</td></tr>'

    # 需要用户操作的事项
    action_items = []
    if stats.get("api_keys_list"):
        for k in stats["api_keys_list"]:
            if k.get("balance") in ["待配置", "待查", ""]:
                action_items.append(f"🔑 请配置 <b>{k['provider']}</b> 的 API Key")
    if not action_items:
        action_items = ["✅ 暂无需要你操作的事项"]

    action_html = "".join(f"<li>{item}</li>" for item in action_items)

    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, "PingFang SC", sans-serif; background:#f5f5f5; margin:0; padding:20px; }}
  .container {{ max-width:600px; margin:0 auto; background:#fff; border-radius:12px; overflow:hidden; box-shadow:0 2px 12px rgba(0,0,0,0.1); }}
  .header {{ background:linear-gradient(135deg,#1a1a2e,#16213e); color:#fff; padding:24px; }}
  .header h1 {{ margin:0; font-size:20px; }}
  .header p {{ margin:4px 0 0; opacity:0.7; font-size:13px; }}
  .section {{ padding:20px 24px; border-bottom:1px solid #f0f0f0; }}
  .section h2 {{ font-size:15px; color:#333; margin:0 0 12px; }}
  .badge {{ display:inline-block; padding:2px 8px; border-radius:4px; font-size:12px; }}
  .badge-green {{ background:#e8f5e9; color:#2e7d32; }}
  .badge-red {{ background:#ffebee; color:#c62828; }}
  .badge-blue {{ background:#e3f2fd; color:#1565c0; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  td {{ padding:6px 8px; border-bottom:1px solid #f5f5f5; }}
  ul {{ margin:0; padding-left:20px; font-size:14px; line-height:1.8; }}
  .action-box {{ background:#fff8e1; border-left:4px solid #ffc107; padding:12px 16px; border-radius:0 8px 8px 0; }}
  .stats-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }}
  .stat-item {{ text-align:center; background:#f8f9fa; border-radius:8px; padding:10px; }}
  .stat-num {{ font-size:22px; font-weight:bold; color:#1a1a2e; }}
  .stat-label {{ font-size:11px; color:#888; }}
  .footer {{ padding:16px 24px; background:#f8f9fa; font-size:12px; color:#999; text-align:center; }}
  pre {{ background:#f8f9fa; padding:10px; border-radius:6px; font-size:12px; overflow-x:auto; white-space:pre-wrap; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>🤖 AI 记忆系统 · 每日状态报告</h1>
    <p>{now} · Mac Mini (tczadmin@frp-toe.com:36711)</p>
  </div>

  <!-- 需要你操作的事项 -->
  <div class="section">
    <h2>⚡ 需要你操作的事项</h2>
    <div class="action-box">
      <ul>{action_html}</ul>
    </div>
  </div>

  <!-- 记忆系统统计 -->
  <div class="section">
    <h2>🧠 记忆系统状态</h2>
    <div class="stats-grid">
      <div class="stat-item">
        <div class="stat-num">{stats.get("core_memory", 0)}</div>
        <div class="stat-label">核心记忆</div>
      </div>
      <div class="stat-item">
        <div class="stat-num">{stats.get("failures", 0)}</div>
        <div class="stat-label">失败记忆</div>
      </div>
      <div class="stat-item">
        <div class="stat-num">{stats.get("episodes", 0)}</div>
        <div class="stat-label">情境记忆</div>
      </div>
      <div class="stat-item">
        <div class="stat-num">{stats.get("preferences", 0)}</div>
        <div class="stat-label">偏好记忆</div>
      </div>
      <div class="stat-item">
        <div class="stat-num">{stats.get("todos", 0)}</div>
        <div class="stat-label">待办事项</div>
      </div>
      <div class="stat-item">
        <div class="stat-num">{stats.get("api_keys", 0)}</div>
        <div class="stat-label">API Keys</div>
      </div>
    </div>
  </div>

  <!-- API Keys 状态 -->
  <div class="section">
    <h2>🔑 API Keys 状态</h2>
    <table>
      <tr style="background:#f8f9fa;font-weight:bold;font-size:13px;">
        <td>服务</td><td>余额/状态</td>
      </tr>
      {api_html}
    </table>
  </div>

  <!-- 待办事项 -->
  <div class="section">
    <h2>📋 待办事项</h2>
    <ul>{todos_html}</ul>
  </div>

  <!-- 今日缓冲摘要 -->
  <div class="section">
    <h2>📝 今日记忆缓冲（最新内容）</h2>
    <pre>{today_buf[:800]}</pre>
  </div>

  <!-- 系统状态 -->
  <div class="section">
    <h2>💻 Mac 系统状态</h2>
    <table>
      <tr><td>磁盘已用</td><td>{sys_status.get("disk_used","?")}</td></tr>
      <tr><td>磁盘可用</td><td>{sys_status.get("disk_avail","?")}</td></tr>
      <tr><td>磁盘使用率</td><td>{sys_status.get("disk_pct","?")}</td></tr>
    </table>
  </div>

  <!-- 每日正能量 -->
  <div class="section" style="background:linear-gradient(135deg,#667eea,#764ba2);border-radius:8px;padding:20px;margin:16px 0;">
    <h2 style="color:#fff;margin:0 0 10px;font-size:15px;">✨ 今日专属鼓励</h2>
    <p style="color:#fff;margin:0;font-size:14px;line-height:1.7;opacity:0.95;">{daily_praise}</p>
  </div>
  <!-- 每日正能量 -->
  <div class="section" style="background:linear-gradient(135deg,#667eea,#764ba2);border-radius:8px;padding:20px;margin:16px 0;">
    <h2 style="color:#fff;margin:0 0 10px;font-size:15px;">✨ 今日专属鼓励</h2>
    <p style="color:#fff;margin:0;font-size:14px;line-height:1.7;opacity:0.95;">{daily_praise}</p>
  </div>
  <div class="footer">
    此邮件由 Mac Mini 上的 AI 记忆系统自动发送 · 每天 09:00<br>
    如需停止，删除 ~/Library/LaunchAgents/com.ai.daily-report.plist
  </div>
</div>
</body>
</html>
"""
    return html

# ─────────────────────────────────────────────
# 发送邮件
# ─────────────────────────────────────────────
def send_email(subject, html_body, attachments=None):
    msg = MIMEMultipart("mixed")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"]    = FROM_EMAIL
    msg["To"]      = TO_EMAIL
    # HTML 正文
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)
    # 附件
    if attachments:
        for fpath in attachments:
            fpath = Path(fpath)
            if fpath.exists():
                part = MIMEBase("application", "octet-stream")
                part.set_payload(fpath.read_bytes())
                encoders.encode_base64(part)
                filename = fpath.name
                part.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=("utf-8", "", filename)
                )
                msg.attach(part)
                print(f"[附件] 已附上: {filename}")

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(FROM_EMAIL, SMTP_PASS)
            server.sendmail(FROM_EMAIL, [TO_EMAIL], msg.as_string())
        print(f"[邮件] 发送成功 → {TO_EMAIL}")
        return True
    except Exception as e:
        print(f"[邮件] 发送失败: {e}", file=sys.stderr)
        return False

# ─────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────
def main():
    if not load_config():
        print("[错误] 邮件配置未找到，请先运行 setup_email.sh 配置 SMTP")
        print(f"  配置文件路径: {CONFIG_FILE}")
        sys.exit(1)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始生成每日状态报告...")

    stats      = get_db_stats()
    balances   = get_api_balances()
    today_buf  = get_today_buffer()
    sys_status = get_system_status()

    today_str = datetime.now().strftime("%Y-%m-%d")
    weekdays  = ["周一","周二","周三","周四","周五","周六","周日"]
    weekday   = weekdays[datetime.now().weekday()]

    subject   = f"🤖 AI 系统日报 {today_str} {weekday} | 需要你操作的事项"

    # 检查是否有需要操作的事项，修改标题
    action_needed = any(
        k.get("balance") in ["待配置", "待查", ""]
        for k in stats.get("api_keys_list", [])
    )
    if not action_needed:
        subject = f"✅ AI 系统日报 {today_str} {weekday} | 一切正常"

    html = build_html_email(stats, balances, today_buf, sys_status)
    # 附上最新记忆钥匙文件
    key_file = Path.home() / "Desktop" / "TCZ·AI记忆钥匙_最新.md"
    attachments = [key_file] if key_file.exists() else []
    success = send_email(subject, html, attachments=attachments)

    # 记录发送日志
    log_file = Path.home() / "ai_memory" / "logs" / "email.log"
    log_file.parent.mkdir(exist_ok=True)
    with open(log_file, "a") as f:
        status = "OK" if success else "FAIL"
        f.write(f"{datetime.now().isoformat()} [{status}] → {TO_EMAIL}\n")

if __name__ == "__main__":
    main()
