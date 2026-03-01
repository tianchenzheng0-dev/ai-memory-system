# 🧠 AI 记忆系统 v3.1

> 让 AI 真正记住你——六层记忆架构 + 每日自动蒸馏 + 情感系统，支持 macOS / Linux

---

## 特性

- **六层记忆架构**：核心记忆、情境记忆、偏好记忆、失败记忆、洞察积累、关系图谱
- **每日自动蒸馏**：凌晨 00:05 自动提炼当天对话，更新长期记忆
- **每日状态邮件**：09:00 自动发送系统状态、待办事项、记忆健康报告
- **版本自动检查**：日报中自动提示是否有新版本可更新
- **情感系统**：AI 有独立的情绪状态，随对话动态变化
- **SQLite + ChromaDB**：结构化 + 向量双存储

---

## 安装

```bash
# 下载并运行安装向导
curl -sf https://raw.githubusercontent.com/tianchenzheng0-dev/ai-memory-system/main/scripts/setup_email.sh | bash
```

---

## 更新（只更新脚本，不动你的记忆数据）

```bash
bash ~/ai_memory/update.sh
```

更新脚本会：
- ✅ 自动备份旧脚本
- ✅ 下载最新程序文件
- ❌ 绝对不碰 `db/`、`core*.md`、`episodes/`、`insights/` 等记忆数据
- ❌ 绝对不碰 `modules/email_config.json` 等用户配置

---

## 目录结构

```
~/ai_memory/
├── VERSION              # 当前版本号
├── update.sh            # 一键更新脚本
├── daily_report.py      # 每日状态邮件
├── distill.sh           # 每日记忆蒸馏（凌晨自动运行）
├── distill_llm.py       # LLM 蒸馏核心逻辑
├── llm_client.py        # LLM 调用客户端（多模型降级）
├── gen_memory_key.py    # 生成记忆钥匙文件
├── ingest_smart.py      # 智能摄入对话内容
├── memory_query.py      # 记忆查询工具
├── backup_to_cos.py     # 备份到腾讯云 COS
├── restore_from_cos.py  # 从 COS 恢复
├── check_balance.sh     # API 余额检查
├── setup_email.sh       # 邮件配置向导
│
├── db/                  # ← 记忆数据库（不更新）
│   └── memory.db
├── core1.md             # ← 核心记忆（不更新）
├── core2.md
├── episodes/            # ← 情境记忆（不更新）
├── insights/            # ← 洞察积累（不更新）
├── today.md             # ← 今日缓冲（不更新）
└── modules/             # ← 用户配置（不更新）
    ├── email_config.json
    └── passwords.md
```

---

## 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| v3.1 | 2026-03-01 | 加入版本检查机制、记忆健康检查日报、update.sh 一键更新 |
| v3.0 | 2026-02-27 | 六层记忆架构 + SQLite + ChromaDB + 每日蒸馏 |

---

*此仓库由 [tianchenzheng0-dev](https://github.com/tianchenzheng0-dev) 维护*
