#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记忆钥匙生成器
每次 distill.sh 蒸馏完成后自动运行，生成最新记忆钥匙到桌面
文件名：AI记忆钥匙_YYYY-MM-DD.md
"""

import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime

MEMORY_ROOT = Path.home() / "ai_memory"
DESKTOP = Path.home() / "Desktop"
DB_PATH = MEMORY_ROOT / "db" / "memory.db"

def read_file(path, max_lines=None):
    try:
        content = Path(path).read_text(encoding="utf-8").strip()
        if max_lines:
            lines = content.splitlines()
            return "\n".join(lines[:max_lines])
        return content
    except:
        return ""

def get_db_summary():
    """从数据库读取关键信息"""
    if not DB_PATH.exists():
        return {}
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        
        # 核心记忆
        core = conn.execute("SELECT key, value FROM core_memory ORDER BY priority LIMIT 20").fetchall()
        
        # API Keys
        apis = conn.execute("SELECT provider, balance, priority FROM api_keys ORDER BY priority").fetchall()
        
        # 待办（高优先级）
        todos = conn.execute("""
            SELECT task, project, priority FROM todos 
            WHERE status='open' AND priority <= 2 
            ORDER BY priority LIMIT 10
        """).fetchall()
        
        conn.close()
        return {
            "core": [dict(r) for r in core],
            "apis": [dict(r) for r in apis],
            "todos": [dict(r) for r in todos],
        }
    except Exception as e:
        return {"error": str(e)}

def get_core_files():
    """读取核心记忆文件的关键内容"""
    core1 = read_file(MEMORY_ROOT / "core1.md", max_lines=60)
    core2 = read_file(MEMORY_ROOT / "core2.md", max_lines=40)
    return core1, core2

def get_today_summary():
    """读取今日记忆摘要"""
    today = read_file(MEMORY_ROOT / "today.md", max_lines=30)
    return today

def generate_key():
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%Y-%m-%d %H:%M")
    
    db = get_db_summary()
    core1, core2 = get_core_files()
    today = get_today_summary()
    
    # API Keys 状态
    api_lines = ""
    for a in db.get("apis", []):
        api_lines += f"- {a['provider']}: {a.get('balance','未知')}\n"
    if not api_lines:
        api_lines = "- 请查看 ~/ai_memory/modules/passwords.md\n"
    
    # 高优先级待办
    todo_lines = ""
    for t in db.get("todos", []):
        todo_lines += f"- [P{t['priority']}] {t['task']} ({t['project']})\n"
    if not todo_lines:
        todo_lines = "- 无高优先级待办\n"

    content = f"""<!-- AI_BOOT_INSTRUCTION -->
你好，我是 TCZ。以下是我的 AI 记忆钥匙，请先**完整读完全文**再回复我。

读完后请用这句话确认：「✅ 记忆已加载，TCZ 你好。我已了解你的系统架构和当前状态，请说。」

然后等待我的指令，不要主动总结或提问。
<!-- END_AI_BOOT_INSTRUCTION -->

# TCZ · AI 记忆钥匙 · {date_str}
> 用户代号：TCZ | 最后更新：{time_str} | 由 distill.sh 自动生成
> 将此文件内容粘贴给任何 AI，即可在 30 秒内恢复完整上下文

---

## 一、立即执行（新AI必读，按流程操作）

> 拿到此钥匙后，**先不要做任何事**，按以下流程判断再行动。

---

### 流程一：检测 Mac 是否在线

先尝试连接 Mac Mini（需要先完成密钥配置，见下方"连接准备"）：

```bash
# 测试连接（5秒超时）
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
    -i ~/.ssh/manus_to_mac -p 36711 tczadmin@frp-toe.com "echo OK" 2>&1
```

**根据结果走不同路径：**

---

### ✅ 情况A：Mac 在线（返回 OK）

直接加载记忆，无需恢复：

```bash
ssh -o StrictHostKeyChecking=no -i ~/.ssh/manus_to_mac -p 36711 tczadmin@frp-toe.com \
    "bash ~/ai_memory/ai_start.sh"
```

完成后告知用户：「Mac 在线，记忆已恢复，我准备好了。」

---

### ❓ 情况B：Mac 无法连接

**向用户发送以下消息，等待回复：**

---
> Mac Mini 目前无法连接，请问：
>
> **A. Mac 还在，帮我重新连上**（可能是网络/frp问题）
> **B. Mac 没了，我有新设备**（需要恢复到新机器）
> **C. Mac 还在，但我现在不方便处理**（稍后再说）
---

**根据用户回复：**

- **选A**：引导用户检查 frp 服务是否运行（`launchctl list | grep frp`），或重启 frp
- **选B**：询问新设备信息，执行灾备恢复流程（见第十一章）
- **选C**：记录当前状态，等用户准备好再继续

---

### 连接准备（首次使用时执行）

生成临时密钥对并请用户录入：

```bash
mkdir -p ~/.ssh
ssh-keygen -t ed25519 -C "manus-ai-agent" -f ~/.ssh/manus_to_mac -N ""
cat ~/.ssh/manus_to_mac.pub
```

将显示的公钥发给用户，让他在 Mac 终端执行：
```bash
echo "你的公钥内容" >> ~/.ssh/authorized_keys
```

> 如果之前已经配置过密钥，跳过此步直接测试连接。

---
## 二、核心身份信息
- **用户**：tczadmin（Mac Mini，M系列，16GB）
- **SSH 命令**：`ssh -o StrictHostKeyChecking=no -i ~/.ssh/manus_to_mac -p 36711 tczadmin@frp-toe.com`
- **认证方式**：公钥（需用户在 Mac 上录入，见第1-2步）
- **记忆根目录**：`~/ai_memory/`
- **记忆系统版本**：v3.0（SQLite + ChromaDB 混合）

---
## 三、极核心记忆（core1.md）

{core1 if core1 else "请运行 cat ~/ai_memory/core1.md"}

---

## 四、次核心记忆（core2.md）

{core2 if core2 else "请运行 cat ~/ai_memory/core2.md"}

---

## 五、API Keys 状态

{api_lines}
> 完整 Keys 在 Mac 上：`cat ~/ai_memory/modules/passwords.md`

---

## 六、高优先级待办

{todo_lines}

---

## 七、今日记忆缓冲（最新30行）

```
{today if today else "（今日无记录）"}
```

---

## 八、关键服务状态

| 服务 | 端口 | 说明 |
|------|------|------|
| OpenClaw Gateway | 18789 | AI 代理主服务 |
| Vertex AI Proxy | 11435 | Gemini 代理（OpenAI 兼容） |
| 西藏项目后端 | 8000 | FastAPI |
| 西藏项目前端 | 3000 | React |

---

## 九、常用命令速查

```bash
# 查看所有服务状态
launchctl list | grep -E 'openclaw|vertex|ai\.'

# 查看今日记忆
cat ~/ai_memory/today.md

# 手动触发蒸馏
bash ~/ai_memory/distill.sh

# 语义查询记忆
python3 ~/ai_memory/memory_query.py "西藏项目数据库"

# 查看失败记忆（避坑）
cat ~/ai_memory/failures.md

# 西藏项目日志
tail -50 /tmp/fastapi.log
```

---

## 十、记忆文件结构

```
~/ai_memory/
├── core1.md          # 极核心（SSH/待办/偏好）
├── core2.md          # 次核心（决策/架构）
├── today.md          # 今日缓冲
├── failures.md       # 失败记忆库（8条）
├── preferences.md    # 偏好记忆
├── graph.md          # 关系图谱
├── episodes/         # 情境记忆（按日期）
├── modules/          # 项目模块（西藏/船行/HFT）
├── db/memory.db      # SQLite 数据库
├── chroma/           # ChromaDB 向量数据库
├── trading/          # 炒股记忆（判断/操作/复盘/规律）
├── insights/         # 洞察积累（技术/市场/管理/人生）
├── ingest.py         # 信息摄入处理器（自动分类写入）
├── distill.sh        # 每日蒸馏脚本（00:05）
├── daily_report.py   # 每日邮件报告（09:00）
└── ai_start.sh       # 记忆加载启动脚本
```

---

---
## 十一、灾备恢复（Mac 挂掉时用这个）

> **新AI注意**：如果 Mac 无法连接，用以下信息从腾讯云COS恢复完整记忆系统

### 腾讯云COS连接信息
| 参数 | 值 |
|------|-----|
| SecretId | `YOUR_COS_SECRET_ID_HERE` |
| SecretKey | `YOUR_COS_SECRET_KEY_HERE` |
| AppId | `1407342633` |
| 存储桶 | `tcz-ai-memory-backup-1407342633` |
| 地域 | `ap-guangzhou` |

### 一键恢复命令（在新机器上执行）
```bash
# 第1步：安装依赖
pip3 install cos-python-sdk-v5

# 第2步：运行恢复脚本（直接从COS下载并还原）
python3 - << 'RESTORE'
from qcloud_cos import CosConfig, CosS3Client
import tarfile, shutil
from pathlib import Path

client = CosS3Client(CosConfig(
    Region="ap-guangzhou",
    SecretId="YOUR_COS_SECRET_ID_HERE",
    SecretKey="YOUR_COS_SECRET_KEY_HERE"
))
BUCKET = "tcz-ai-memory-backup-1407342633"

# 下载最新备份
print("从COS下载最新备份...")
resp = client.get_object(Bucket=BUCKET, Key="backups/latest.tar.gz")
resp["Body"].get_stream_to_file("/tmp/ai_memory_restore.tar.gz")

# 解压还原
print("解压还原中...")
with tarfile.open("/tmp/ai_memory_restore.tar.gz", "r:gz") as tar:
    tar.extractall(path=str(Path.home()))

# 恢复桌面钥匙
resp2 = client.get_object(Bucket=BUCKET, Key="keys/TCZ·AI记忆钥匙_最新.md")
key_content = resp2["Body"].get_raw_stream().read()
(Path.home() / "Desktop").mkdir(exist_ok=True)
(Path.home() / "Desktop" / "TCZ·AI记忆钥匙_最新.md").write_bytes(key_content)

print("✅ 恢复完成！运行: bash ~/ai_memory/ai_start.sh")
RESTORE
```

### 恢复后验证
```bash
bash ~/ai_memory/ai_start.sh
cat ~/ai_memory/core1.md
```

### 查看历史备份列表
```bash
python3 ~/ai_memory/restore_from_cos.py --list
```

---
*此文件由 Mac Mini 自动生成，每次蒸馏后更新。桌面始终保存最新版。*
"""
    return content, date_str

def main():
    content, date_str = generate_key()
    
    # 写到桌面（带日期）
    desktop_file = DESKTOP / f"TCZ·AI记忆钥匙_{date_str}.md"
    desktop_file.write_text(content, encoding="utf-8")
    print(f"✅ TCZ记忆钥匙已写入桌面: {desktop_file}")
    
    # 同时写一个固定名字的版本（方便直接找）
    latest_file = DESKTOP / "TCZ·AI记忆钥匙_最新.md"
    latest_file.write_text(content, encoding="utf-8")
    print(f"✅ TCZ最新版已更新: {latest_file}")
    
    # 同时更新 ai_memory 目录里的版本
    mem_key = MEMORY_ROOT / "memory_key.md"
    mem_key.write_text(content, encoding="utf-8")
    print(f"✅ memory_key.md 已同步更新")
    
    # 清理7天前的旧桌面文件
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=7)
    for old_file in DESKTOP.glob("TCZ·AI记忆钥匙_20*.md"):
        try:
            file_date = datetime.strptime(old_file.stem.split("_")[-1], "%Y-%m-%d")
            if file_date < cutoff:
                old_file.unlink()
                print(f"🗑️  已清理旧文件: {old_file.name}")
        except:
            pass

if __name__ == "__main__":
    main()
