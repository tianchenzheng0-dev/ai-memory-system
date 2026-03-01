#!/bin/bash
# ─────────────────────────────────────────────────────────────
# AI 记忆系统 - 一键更新脚本
# 只更新程序脚本，绝对不碰你的记忆数据
# 用法：bash ~/ai_memory/update.sh
# ─────────────────────────────────────────────────────────────

set -e

MEMORY_ROOT="$HOME/ai_memory"
GITHUB_RAW="https://raw.githubusercontent.com/tianchenzheng0-dev/ai-memory-system/main"
BACKUP_DIR="$MEMORY_ROOT/backup_scripts/$(date +%Y%m%d_%H%M%S)"

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     AI 记忆系统 - 版本更新程序          ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════╝${NC}"
echo ""

# ── 1. 检查当前版本 ──
LOCAL_VERSION="unknown"
if [ -f "$MEMORY_ROOT/VERSION" ]; then
    LOCAL_VERSION=$(cat "$MEMORY_ROOT/VERSION" | tr -d '[:space:]')
fi

echo -e "📌 当前版本：${YELLOW}v${LOCAL_VERSION}${NC}"

# ── 2. 获取最新版本号 ──
echo -n "🔍 检查最新版本..."
REMOTE_VERSION=$(curl -sf --connect-timeout 10 "$GITHUB_RAW/VERSION" | tr -d '[:space:]') || {
    echo -e "\n${RED}❌ 无法连接到 GitHub，请检查网络后重试${NC}"
    exit 1
}
echo -e " ${GREEN}v${REMOTE_VERSION}${NC}"

# ── 3. 比较版本 ──
if [ "$LOCAL_VERSION" = "$REMOTE_VERSION" ]; then
    echo ""
    echo -e "${GREEN}✅ 已是最新版本 v${REMOTE_VERSION}，无需更新${NC}"
    echo ""
    exit 0
fi

echo ""
echo -e "🆕 发现新版本：${GREEN}v${REMOTE_VERSION}${NC}（当前：v${LOCAL_VERSION}）"
echo ""

# ── 4. 备份旧脚本 ──
echo -e "📦 备份旧脚本到 ${YELLOW}backup_scripts/$(basename $BACKUP_DIR)${NC}..."
mkdir -p "$BACKUP_DIR"
for f in "$MEMORY_ROOT"/*.py "$MEMORY_ROOT"/*.sh; do
    [ -f "$f" ] && cp "$f" "$BACKUP_DIR/" 2>/dev/null || true
done
echo -e "   ${GREEN}✅ 备份完成${NC}"

# ── 5. 需要更新的脚本列表（只更新脚本，不动数据）──
SCRIPTS=(
    "scripts/daily_report.py"
    "scripts/distill.sh"
    "scripts/distill_llm.py"
    "scripts/llm_client.py"
    "scripts/gen_memory_key.py"
    "scripts/ingest_smart.py"
    "scripts/backup_to_cos.py"
    "scripts/check_balance.sh"
    "scripts/memory_query.py"
    "scripts/restore_from_cos.py"
    "scripts/ai_start.sh"
    "scripts/setup_email.sh"
    "update.sh"
)

# ── 6. 下载并更新脚本 ──
echo ""
echo "⬇️  正在下载最新脚本..."
UPDATED=0
FAILED=0

for script_path in "${SCRIPTS[@]}"; do
    filename=$(basename "$script_path")
    
    # update.sh 自身放在 MEMORY_ROOT，其他放在 MEMORY_ROOT
    dest="$MEMORY_ROOT/$filename"
    
    if curl -sf --connect-timeout 15 "$GITHUB_RAW/$script_path" -o "${dest}.tmp"; then
        mv "${dest}.tmp" "$dest"
        chmod +x "$dest" 2>/dev/null || true
        echo -e "   ${GREEN}✅ $filename${NC}"
        UPDATED=$((UPDATED + 1))
    else
        rm -f "${dest}.tmp"
        echo -e "   ${YELLOW}⚠️  $filename（跳过，下载失败）${NC}"
        FAILED=$((FAILED + 1))
    fi
done

# ── 7. 更新本地版本号 ──
echo "$REMOTE_VERSION" > "$MEMORY_ROOT/VERSION"

# ── 8. 完成报告 ──
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ✅ 更新完成！                           ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "  版本：v${LOCAL_VERSION} → ${GREEN}v${REMOTE_VERSION}${NC}"
echo -e "  更新：${GREEN}${UPDATED} 个文件${NC}"
[ $FAILED -gt 0 ] && echo -e "  跳过：${YELLOW}${FAILED} 个文件${NC}"
echo -e "  备份：${YELLOW}$BACKUP_DIR${NC}"
echo ""
echo -e "💡 你的记忆数据完好无损，只有程序脚本被更新了"
echo -e "💡 如需回滚，备份文件在上方目录中"
echo ""
