#!/bin/bash
# ============================================================
# AI 记忆系统启动脚本 v3.0
# 支持：分层加载 + 混合查询 + 模块动态加载
# 用法：
#   ./ai_start.sh              # 加载核心层（core1 + core2）
#   ./ai_start.sh --full       # 加载全部记忆
#   ./ai_start.sh --query "关键词"  # 语义查询
#   ./ai_start.sh --module passwords  # 加载指定模块
#   ./ai_start.sh --project tibet     # 加载项目记忆
#   ./ai_start.sh --today      # 显示今日缓冲区
#   ./ai_start.sh --stats      # 显示记忆统计
# ============================================================

MEMORY_ROOT="$HOME/ai_memory"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 颜色
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# ─────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────
print_header() {
    echo -e "${BLUE}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║     AI 持久化记忆系统 v3.0 (混合架构)        ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════╝${NC}"
    echo -e "${YELLOW}时间: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo ""
}

load_file() {
    local label="$1"
    local fpath="$2"
    if [ -f "$fpath" ]; then
        echo -e "${GREEN}=== $label ===${NC}"
        cat "$fpath"
        echo ""
    else
        echo -e "${RED}[缺失] $fpath${NC}"
    fi
}

# ─────────────────────────────────────────────
# 参数解析
# ─────────────────────────────────────────────
MODE="core"
QUERY=""
MODULE=""
PROJECT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --full)      MODE="full" ;;
        --today)     MODE="today" ;;
        --stats)     MODE="stats" ;;
        --query|-q)  MODE="query"; QUERY="$2"; shift ;;
        --module|-m) MODE="module"; MODULE="$2"; shift ;;
        --project|-p) MODE="project"; PROJECT="$2"; shift ;;
        --help|-h)
            echo "用法: $0 [选项]"
            echo "  --full          加载全部记忆"
            echo "  --query <词>    语义查询"
            echo "  --module <名>   加载指定模块"
            echo "  --project <名>  加载项目记忆"
            echo "  --today         显示今日缓冲区"
            echo "  --stats         显示记忆统计"
            exit 0
            ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
    shift
done

# ─────────────────────────────────────────────
# 执行
# ─────────────────────────────────────────────
print_header

case "$MODE" in
    core)
        echo -e "${YELLOW}[模式] 核心层加载（最小上下文）${NC}"
        echo ""
        load_file "核心层 1 (极核)" "$MEMORY_ROOT/core1.md"
        load_file "核心层 2 (次核)" "$MEMORY_ROOT/core2.md"
        echo -e "${YELLOW}提示: 使用 --full 加载全部，--query <词> 语义检索${NC}"
        ;;

    full)
        echo -e "${YELLOW}[模式] 全量加载${NC}"
        echo ""
        load_file "核心层 1" "$MEMORY_ROOT/core1.md"
        load_file "核心层 2" "$MEMORY_ROOT/core2.md"
        load_file "偏好记忆" "$MEMORY_ROOT/preferences.md"
        load_file "关系图谱" "$MEMORY_ROOT/graph.md"
        # 加载所有项目
        if [ -d "$MEMORY_ROOT/projects" ]; then
            for f in "$MEMORY_ROOT/projects"/*.md; do
                [ -f "$f" ] && load_file "项目: $(basename $f .md)" "$f"
            done
        fi
        # 加载最近3个情境记忆
        if [ -d "$MEMORY_ROOT/episodes" ]; then
            for f in $(ls -t "$MEMORY_ROOT/episodes"/*.md 2>/dev/null | head -3); do
                load_file "情境: $(basename $f .md)" "$f"
            done
        fi
        load_file "今日缓冲" "$MEMORY_ROOT/today.md"
        ;;

    today)
        load_file "今日缓冲区" "$MEMORY_ROOT/today.md"
        ;;

    stats)
        python3 "$MEMORY_ROOT/memory_query.py" --stats 2>/dev/null || {
            echo "记忆文件统计:"
            echo "  core1.md:       $(wc -l < $MEMORY_ROOT/core1.md 2>/dev/null || echo 0) 行"
            echo "  core2.md:       $(wc -l < $MEMORY_ROOT/core2.md 2>/dev/null || echo 0) 行"
            echo "  preferences.md: $(wc -l < $MEMORY_ROOT/preferences.md 2>/dev/null || echo 0) 行"
            echo "  failures.md:    $(wc -l < $MEMORY_ROOT/failures.md 2>/dev/null || echo 0) 行"
            echo "  graph.md:       $(wc -l < $MEMORY_ROOT/graph.md 2>/dev/null || echo 0) 行"
            echo "  episodes/:      $(ls $MEMORY_ROOT/episodes/*.md 2>/dev/null | wc -l) 个文件"
            echo "  projects/:      $(ls $MEMORY_ROOT/projects/*.md 2>/dev/null | wc -l) 个文件"
        }
        ;;

    query)
        if [ -z "$QUERY" ]; then
            echo -e "${RED}错误: --query 需要提供查询词${NC}"
            exit 1
        fi
        echo -e "${YELLOW}[语义查询] '$QUERY'${NC}"
        python3 "$MEMORY_ROOT/memory_query.py" --query "$QUERY" 2>/dev/null || {
            # 降级：grep 关键词搜索
            echo "[降级模式] 使用 grep 关键词搜索..."
            grep -r "$QUERY" "$MEMORY_ROOT" --include="*.md" -l 2>/dev/null | while read f; do
                echo -e "${GREEN}--- $f ---${NC}"
                grep -n "$QUERY" "$f" | head -5
                echo ""
            done
        }
        ;;

    module)
        if [ -z "$MODULE" ]; then
            echo -e "${RED}错误: --module 需要提供模块名${NC}"
            exit 1
        fi
        # 搜索路径
        CANDIDATES=(
            "$MEMORY_ROOT/modules/${MODULE}.md"
            "$MEMORY_ROOT/${MODULE}.md"
            "$MEMORY_ROOT/projects/${MODULE}.md"
        )
        FOUND=0
        for f in "${CANDIDATES[@]}"; do
            if [ -f "$f" ]; then
                load_file "模块: $MODULE" "$f"
                FOUND=1
                break
            fi
        done
        if [ $FOUND -eq 0 ]; then
            echo -e "${RED}[未找到] 模块 '$MODULE'${NC}"
            echo "可用模块:"
            ls "$MEMORY_ROOT/modules/"*.md 2>/dev/null | xargs -I{} basename {} .md
        fi
        ;;

    project)
        if [ -z "$PROJECT" ]; then
            echo -e "${RED}错误: --project 需要提供项目名${NC}"
            exit 1
        fi
        load_file "项目: $PROJECT" "$MEMORY_ROOT/projects/${PROJECT}.md"
        ;;
esac

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo -e "${YELLOW}记忆系统就绪 | $(date '+%H:%M') | 输入 --help 查看更多选项${NC}"
