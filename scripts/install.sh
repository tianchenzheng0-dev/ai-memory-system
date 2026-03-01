#!/bin/bash
# ============================================================
# TCZ · AI 记忆系统 v3.0 - 一键安装脚本
# 作者：TCZ / Manus Agent
# 仓库：https://github.com/tianchenzheng0-dev/ai-memory-system
# ============================================================

set -e

REPO_BASE="https://raw.githubusercontent.com/tianchenzheng0-dev/ai-memory-system/main"
MEMORY_ROOT="$HOME/ai_memory"
SCRIPTS_DIR="$MEMORY_ROOT/scripts"
LOG="$MEMORY_ROOT/logs/install.log"
VERSION="v3.0.0"

# ── 颜色输出 ──────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
error()   { echo -e "${RED}[✗]${NC} $1"; exit 1; }
section() { echo -e "\n${YELLOW}━━━ $1 ━━━${NC}"; }

echo ""
echo "  ████████╗ ██████╗███████╗    ██████╗ ███████╗"
echo "     ██╔══╝██╔════╝╚══███╔╝    ██╔══██╗██╔════╝"
echo "     ██║   ██║       ███╔╝     ██████╔╝███████╗"
echo "     ██║   ██║      ███╔╝      ██╔═══╝ ╚════██║"
echo "     ██║   ╚██████╗███████╗    ██║     ███████║"
echo "     ╚═╝    ╚═════╝╚══════╝    ╚═╝     ╚══════╝"
echo ""
echo "  AI 记忆系统 $VERSION  一键安装程序"
echo "  ─────────────────────────────────────────────"
echo ""

# ── 第 1 步：检测操作系统 ──────────────────────────────────
section "第 1 步：检测环境"
OS="$(uname -s)"
if [ "$OS" = "Darwin" ]; then
    info "检测到 macOS"
    PLIST_DIR="$HOME/Library/LaunchAgents"
    PYTHON="python3"
    PIP="pip3"
elif [ "$OS" = "Linux" ]; then
    info "检测到 Linux"
    PLIST_DIR=""
    PYTHON="python3"
    PIP="pip3"
else
    error "不支持的操作系统：$OS"
fi

# ── 第 2 步：创建目录结构 ──────────────────────────────────
section "第 2 步：创建目录结构"
for dir in \
    "$MEMORY_ROOT" \
    "$MEMORY_ROOT/db" \
    "$MEMORY_ROOT/db/chroma" \
    "$MEMORY_ROOT/episodes" \
    "$MEMORY_ROOT/insights" \
    "$MEMORY_ROOT/logs" \
    "$MEMORY_ROOT/modules" \
    "$MEMORY_ROOT/trading" \
    "$MEMORY_ROOT/projects" \
    "$MEMORY_ROOT/.backup" \
    "$SCRIPTS_DIR"; do
    mkdir -p "$dir"
done
info "目录结构创建完成"

# 创建安装日志
touch "$LOG"
echo "[$(date)] 开始安装 $VERSION" >> "$LOG"

# ── 第 3 步：安装 Python 依赖 ──────────────────────────────
section "第 3 步：安装 Python 依赖"
info "安装 openai..."
$PIP install openai --quiet --upgrade || warn "openai 安装失败，请手动运行：pip3 install openai"

info "安装 chromadb（向量数据库，可能需要1-2分钟）..."
$PIP install chromadb --quiet || warn "chromadb 安装失败，请手动运行：pip3 install chromadb"

info "安装 requests..."
$PIP install requests --quiet || warn "requests 安装失败"

info "Python 依赖安装完成"

# ── 第 4 步：下载核心脚本 ──────────────────────────────────
section "第 4 步：下载核心脚本"
SCRIPTS=(
    "distill.sh"
    "distill_llm.py"
    "daily_report.py"
    "gen_memory_key.py"
    "ingest_smart.py"
    "llm_client.py"
    "memory_query.py"
    "setup_email.sh"
    "check_balance.sh"
    "backup_to_cos.py"
    "restore_from_cos.py"
    "update.sh"
)

for script in "${SCRIPTS[@]}"; do
    url="$REPO_BASE/scripts/$script"
    dest="$SCRIPTS_DIR/$script"
    if curl -fsSL "$url" -o "$dest" 2>/dev/null; then
        chmod +x "$dest"
        info "下载 $script"
    else
        warn "下载失败：$script（跳过）"
    fi
done

# 兼容旧路径：在 ai_memory 根目录也创建软链接
for script in "${SCRIPTS[@]}"; do
    src="$SCRIPTS_DIR/$script"
    link="$MEMORY_ROOT/$script"
    [ -f "$src" ] && [ ! -e "$link" ] && ln -sf "$src" "$link"
done

# ── 第 5 步：初始化 SQLite 数据库 ─────────────────────────
section "第 5 步：初始化 SQLite 数据库"
DB_PATH="$MEMORY_ROOT/db/memory.db"
if [ ! -f "$DB_PATH" ]; then
    $PYTHON - << 'PYEOF'
import sqlite3, os
from pathlib import Path

db = Path.home() / "ai_memory" / "db" / "memory.db"
conn = sqlite3.connect(str(db))
c = conn.cursor()

c.executescript("""
CREATE TABLE IF NOT EXISTS core_memory (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    layer        TEXT NOT NULL,
    module       TEXT NOT NULL,
    content      TEXT NOT NULL,
    frequency    TEXT DEFAULT 'mid',
    confidence   INTEGER DEFAULT 3,
    anchors      TEXT DEFAULT '',
    created_at   TEXT DEFAULT (datetime('now','localtime')),
    updated_at   TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS relationships (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_from  TEXT NOT NULL,
    entity_to    TEXT NOT NULL,
    relation     TEXT NOT NULL,
    note         TEXT DEFAULT '',
    created_at   TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS preferences (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category     TEXT NOT NULL,
    key          TEXT NOT NULL,
    value        TEXT NOT NULL,
    confidence   INTEGER DEFAULT 3,
    updated_at   TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(category, key)
);
CREATE TABLE IF NOT EXISTS failures (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code         TEXT UNIQUE,
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
    priority     INTEGER DEFAULT 3,
    status       TEXT DEFAULT 'open',
    due_date     TEXT DEFAULT '',
    created_at   TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS api_keys (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    provider     TEXT UNIQUE NOT NULL,
    key_hint     TEXT NOT NULL,
    balance      TEXT DEFAULT 'unknown',
    priority     INTEGER DEFAULT 5,
    updated_at   TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_core_layer    ON core_memory(layer);
CREATE INDEX IF NOT EXISTS idx_core_freq     ON core_memory(frequency);
CREATE INDEX IF NOT EXISTS idx_failures_code ON failures(code);
CREATE INDEX IF NOT EXISTS idx_episodes_date ON episodes(date);
CREATE INDEX IF NOT EXISTS idx_todos_status  ON todos(status);
""")
conn.commit()
conn.close()
print("SQLite 数据库初始化完成")
PYEOF
    info "SQLite 数据库初始化完成（7张表）"
else
    info "SQLite 数据库已存在，跳过初始化"
fi

# ── 第 6 步：初始化 ChromaDB ───────────────────────────────
section "第 6 步：初始化 ChromaDB 向量数据库"
$PYTHON - << 'PYEOF'
try:
    import chromadb
    from pathlib import Path
    chroma_path = Path.home() / "ai_memory" / "db" / "chroma"
    client = chromadb.PersistentClient(path=str(chroma_path))
    # 创建三个默认集合
    for name in ["memory_core", "memory_episodes", "memory_insights"]:
        try:
            client.get_or_create_collection(name)
        except:
            pass
    print("ChromaDB 向量数据库初始化完成（3个集合）")
except ImportError:
    print("警告：chromadb 未安装，向量搜索功能不可用")
except Exception as e:
    print(f"警告：ChromaDB 初始化失败：{e}")
PYEOF
info "ChromaDB 初始化完成"

# ── 第 7 步：创建配置文件模板 ──────────────────────────────
section "第 7 步：创建配置文件模板"

# schema.json
SCHEMA_FILE="$MEMORY_ROOT/schema.json"
if [ ! -f "$SCHEMA_FILE" ]; then
    curl -fsSL "$REPO_BASE/templates/schema.json" -o "$SCHEMA_FILE" 2>/dev/null || \
    cat > "$SCHEMA_FILE" << 'JSONEOF'
{
  "_meta": {
    "version": "1.0",
    "description": "AI记忆系统模块注册表，AI每次摄入新内容时参考此表判断写入位置",
    "auto_update": true
  },
  "layers": {
    "core1": {"description": "极核心层，每次必读。待办、用户偏好、记忆导航", "file": "core1.md"},
    "core2": {"description": "次核心层，每次必读。架构决策、工作规范、配置信息", "file": "core2.md"},
    "module": {"description": "项目/主题模块层，按需加载", "path": "modules/"},
    "episode": {"description": "情境记忆层，按日期存储", "path": "episodes/YYYY-MM-DD.md"},
    "insight": {"description": "洞察积累层", "path": "insights/"},
    "trading": {"description": "炒股记忆层", "path": "trading/"}
  }
}
JSONEOF
    info "schema.json 创建完成"
fi

# email_config.json 模板
EMAIL_CONFIG="$MEMORY_ROOT/modules/email_config.json"
if [ ! -f "$EMAIL_CONFIG" ]; then
    cat > "$EMAIL_CONFIG" << 'JSONEOF'
{
  "from_email": "",
  "smtp_pass": "",
  "to_email": "",
  "smtp_host": "smtp.qq.com",
  "smtp_port": 587,
  "configured": false
}
JSONEOF
    info "email_config.json 模板创建完成"
fi

# api_providers.md 模板
API_FILE="$MEMORY_ROOT/modules/api_providers.md"
if [ ! -f "$API_FILE" ]; then
    cat > "$API_FILE" << 'MDEOF'
# API 配置

## LLM API Keys
<!-- 安装后通过 setup_email.sh 配置，或手动填写 -->

| 服务商 | API Key | 优先级 |
|--------|---------|--------|
| Groq   | YOUR_GROQ_API_KEY | 1 |
| Kimi   | YOUR_KIMI_API_KEY | 2 |
| DeepSeek | YOUR_DEEPSEEK_API_KEY | 3 |
MDEOF
    info "api_providers.md 模板创建完成"
fi

# core1.md / core2.md 初始化
for f in core1.md core2.md today.md preferences.md failures.md graph.md; do
    [ ! -f "$MEMORY_ROOT/$f" ] && touch "$MEMORY_ROOT/$f" && info "创建 $f"
done

# ── 第 8 步：注册 launchd 定时任务（仅 macOS）────────────
if [ "$OS" = "Darwin" ]; then
    section "第 8 步：注册定时任务（macOS launchd）"
    mkdir -p "$PLIST_DIR"
    USERNAME=$(whoami)

    # 蒸馏任务：每天 00:05
    DISTILL_PLIST="$PLIST_DIR/com.ai.memory.distill.plist"
    if [ ! -f "$DISTILL_PLIST" ]; then
        cat > "$DISTILL_PLIST" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ai.memory.distill</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$SCRIPTS_DIR/distill.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>0</integer>
        <key>Minute</key>
        <integer>5</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$MEMORY_ROOT/logs/distill_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$MEMORY_ROOT/logs/distill_stderr.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
PLISTEOF
        launchctl load "$DISTILL_PLIST" 2>/dev/null && info "蒸馏任务注册成功（每天 00:05）" || warn "蒸馏任务注册失败，请手动运行：launchctl load $DISTILL_PLIST"
    else
        info "蒸馏任务已存在，跳过"
    fi

    # 日报任务：每天 09:00
    REPORT_PLIST="$PLIST_DIR/com.ai.daily-report.plist"
    if [ ! -f "$REPORT_PLIST" ]; then
        cat > "$REPORT_PLIST" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ai.daily-report</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>$SCRIPTS_DIR/daily_report.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$MEMORY_ROOT/logs/daily_report_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$MEMORY_ROOT/logs/daily_report_stderr.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
PLISTEOF
        launchctl load "$REPORT_PLIST" 2>/dev/null && info "日报任务注册成功（每天 09:00）" || warn "日报任务注册失败，请手动运行：launchctl load $REPORT_PLIST"
    else
        info "日报任务已存在，跳过"
    fi

elif [ "$OS" = "Linux" ]; then
    section "第 8 步：注册定时任务（Linux crontab）"
    (crontab -l 2>/dev/null | grep -v "distill.sh\|daily_report.py"; \
     echo "5 0 * * * /bin/bash $SCRIPTS_DIR/distill.sh >> $MEMORY_ROOT/logs/distill_stdout.log 2>&1"; \
     echo "0 9 * * * $PYTHON $SCRIPTS_DIR/daily_report.py >> $MEMORY_ROOT/logs/daily_report_stdout.log 2>&1") | crontab -
    info "crontab 定时任务注册完成"
fi

# ── 第 9 步：写入版本号 ────────────────────────────────────
section "第 9 步：写入版本信息"
echo "$VERSION" > "$MEMORY_ROOT/.version"
echo "[$(date)] 安装完成 $VERSION" >> "$LOG"
info "版本号 $VERSION 已写入"

# ── 完成 ──────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   🎉  AI 记忆系统 $VERSION 安装完成！      ║${NC}"
echo -e "${GREEN}╠════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  下一步：配置邮箱                          ║${NC}"
echo -e "${GREEN}║  运行：bash $SCRIPTS_DIR/setup_email.sh    ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"
echo ""
echo "  安装目录：$MEMORY_ROOT"
echo "  日志文件：$LOG"
echo ""
