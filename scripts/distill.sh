#!/bin/bash
# ── 蒸馏进程锁：防止两个AI同时运行蒸馏 ──
python3 "$HOME/ai_memory/memory_lock.py" --distill-acquire 2>/dev/null
LOCK_STATUS=$?
if [ $LOCK_STATUS -ne 0 ]; then
    echo "[distill] $(date '+%H:%M:%S') 另一个蒸馏进程正在运行，本次跳过"
    exit 0
fi
# 注册退出时自动释放锁
trap 'python3 "$HOME/ai_memory/memory_lock.py" --distill-release 2>/dev/null' EXIT
# ============================================================
# AI 记忆蒸馏脚本 - distill.sh
# 每日 00:05 由 launchd 自动触发
# 功能：将今日记忆(today.md)蒸馏分类写入各层记忆文件
# ============================================================

MEMORY_DIR="$HOME/ai_memory"
TODAY_FILE="$MEMORY_DIR/today.md"
LOG_FILE="$MEMORY_DIR/logs/distill.log"
BACKUP_DIR="$MEMORY_DIR/.backup"
TIMESTAMP=$(date "+%Y-%m-%d %H:%M")
DATE_YESTERDAY=$(date -v-1d "+%Y-%m-%d" 2>/dev/null || date -d "yesterday" "+%Y-%m-%d")

# 加载环境变量（API Keys）
source ~/.zshrc 2>/dev/null || true

mkdir -p "$BACKUP_DIR"

log() {
    echo "[$TIMESTAMP] $1" | tee -a "$LOG_FILE"
}

log "========== 开始蒸馏 =========="

# ---- 检查今日记忆是否有内容 ----
TODAY_CONTENT=$(cat "$TODAY_FILE" 2>/dev/null)
TODAY_LINES=$(wc -l < "$TODAY_FILE" 2>/dev/null || echo 0)

if [ "$TODAY_LINES" -lt 5 ]; then
    log "今日记忆内容不足，跳过蒸馏"
    exit 0
fi

# ---- 备份今日记忆 ----
cp "$TODAY_FILE" "$BACKUP_DIR/today_${DATE_YESTERDAY}.md"
log "已备份今日记忆到 $BACKUP_DIR/today_${DATE_YESTERDAY}.md"

# ---- 构建蒸馏 Prompt ----
PROMPT="你是一个AI记忆管理系统。请分析以下今日对话记录，并按JSON格式输出蒸馏结果。

今日记忆内容：
---
${TODAY_CONTENT}
---

请输出以下JSON格式（所有字段都是字符串，用\\n表示换行）：
{
  \"core1_update\": \"需要更新到极核心层的内容（SSH变更、最新待办、用户偏好变化），如无变化则为空字符串\",
  \"core2_update\": \"需要更新到次核心层的内容（重要决策、架构变更、跨项目信息），如无变化则为空字符串\",
  \"tibet_append\": \"需要追加到西藏项目层的内容，如无则为空字符串\",
  \"ship_append\": \"需要追加到船行天下项目层的内容，如无则为空字符串\",
  \"hft_append\": \"需要追加到高频交易项目层的内容，如无则为空字符串\",
  \"tibet_log\": \"西藏项目的操作日志条目（一行），如无则为空字符串\",
  \"ship_log\": \"船行天下项目的操作日志条目（一行），如无则为空字符串\",
  \"hft_log\": \"高频交易项目的操作日志条目（一行），如无则为空字符串\",
  \"summary\": \"今日工作的一句话总结\"
}

只输出JSON，不要任何其他内容。"

# ---- 多级降级链调用AI ----
DISTILL_RESULT=""
API_USED=""



# 降级链：Gemini(Vertex AI) → Kimi → OpenRouter(Groq → Claude)
# 由 distill_llm.py 统一处理，每步有 threading 超时保护，不会永久卡死
echo "$PROMPT" > "$HOME/ai_memory/.distill_prompt_tmp.txt"
log "调用 LLM 降级链（Gemini → Kimi → OpenRouter）..."
DISTILL_RESULT=$(python3 "$HOME/ai_memory/distill_llm.py" "$HOME/ai_memory/.distill_prompt_tmp.txt" 2>>"$LOG_FILE")
DISTILL_EXIT=$?
if [ $DISTILL_EXIT -ne 0 ]; then
    log "❌ 所有AI API均失败！今日记忆保留，明日重试。"
    sed -i '' "s/distill_status: .*/distill_status: failed/" "$TODAY_FILE" 2>/dev/null || \
    sed -i "s/distill_status: .*/distill_status: failed/" "$TODAY_FILE"
    exit 1
fi
if echo "$DISTILL_RESULT" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
    API_USED="LLM降级链"
    log "✅ LLM 调用成功"
else
    log "❌ LLM 返回了无效 JSON，今日记忆保留。"
    sed -i '' "s/distill_status: .*/distill_status: invalid_json/" "$TODAY_FILE" 2>/dev/null || \
    sed -i "s/distill_status: .*/distill_status: invalid_json/" "$TODAY_FILE"
    exit 1
fi
log "✅ 蒸馏成功，使用模型: $API_USED"

# ---- 解析JSON并写入各层 ----
python3 - <<PYEOF
import json, os, sys
from datetime import datetime

memory_dir = os.path.expanduser("~/ai_memory")
result_str = """${DISTILL_RESULT}"""
timestamp = "${TIMESTAMP}"

try:
    result = json.loads(result_str)
except Exception as e:
    print(f"JSON解析失败: {e}", file=sys.stderr)
    sys.exit(1)

def append_to_file(filepath, content, header=None):
    if not content or not content.strip():
        return
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'a', encoding='utf-8') as f:
        if header:
            f.write(f"\n### {header} ({timestamp})\n")
        f.write(content.replace('\\n', '\n') + '\n')

def check_log_size_and_rotate(log_path):
    """日志超过50KB自动滚动"""
    if os.path.exists(log_path) and os.path.getsize(log_path) > 50 * 1024:
        base = log_path.rsplit('_', 1)[0]
        num = int(log_path.rsplit('_', 1)[1].replace('.log', ''))
        new_path = f"{base}_{num+1}.log"
        print(f"日志滚动: {log_path} -> {new_path}")
        return new_path
    return log_path

# 写入各层
if result.get('core2_update'):
    append_to_file(f"{memory_dir}/core2.md", result['core2_update'], "新增决策")

if result.get('tibet_append'):
    append_to_file(f"{memory_dir}/projects/tibet.md", result['tibet_append'], "更新")

if result.get('ship_append'):
    append_to_file(f"{memory_dir}/projects/ship.md", result['ship_append'], "更新")

if result.get('hft_append'):
    append_to_file(f"{memory_dir}/projects/hft.md", result['hft_append'], "更新")

# 写入日志（带滚动）
for proj, key in [('tibet', 'tibet_log'), ('ship', 'ship_log'), ('hft', 'hft_log')]:
    log_path = f"{memory_dir}/logs/{proj}_1.log"
    log_path = check_log_size_and_rotate(log_path)
    if result.get(key):
        with open(log_path, 'a') as f:
            f.write(f"[{timestamp}] {result[key]}\n")

summary = result.get('summary', '今日工作已完成蒸馏')
print(f"蒸馏摘要: {summary}")
PYEOF

if [ $? -eq 0 ]; then
    log "✅ 各层记忆文件更新完成"
    
    # 清空今日记忆，写入新模板
    cat > "$TODAY_FILE" <<TEMPLATE
---
date: $(date "+%Y-%m-%d")
distill_status: pending
distill_target: $(date -v+1d "+%Y-%m-%d" 2>/dev/null || date -d "tomorrow" "+%Y-%m-%d") 00:05
---

## 今日记忆 ($(date "+%Y-%m-%d"))

(今日对话内容将在此追加)
TEMPLATE
    log "✅ 今日记忆已清空，准备接收新内容"
else
    log "❌ 写入各层失败，今日记忆保留"
    sed -i '' "s/distill_status: .*/distill_status: write_failed/" "$TODAY_FILE" 2>/dev/null || \
    sed -i "s/distill_status: .*/distill_status: write_failed/" "$TODAY_FILE"
fi

log "========== 蒸馏结束 =========="

# ---- 蒸馏完成后自动检查剥离 ----
echo "[蒸馏后] 检查是否需要剥离模块..."
bash ~/ai_memory/split_module.sh 2>&1 | tail -20
echo "[完成] 蒸馏 + 剥离检查全部完成"
# ---- 自动更新桌面记忆钥匙 ----
log "正在更新桌面记忆钥匙..."
python3 ~/ai_memory/gen_memory_key.py >> "" 2>&1 && log "✅ 桌面记忆钥匙已更新" || log "⚠️  记忆钥匙更新失败（不影响蒸馏结果）"


# ---- 自动模块合并检测（每7天运行一次）----
MERGE_FLAG="$HOME/ai_memory/.last_merge_check"
DAYS_SINCE=7
if [ -f "$MERGE_FLAG" ]; then
    LAST=$(cat "$MERGE_FLAG")
    NOW=$(date +%s)
    DIFF=$(( (NOW - LAST) / 86400 ))
    DAYS_SINCE=$DIFF
fi
if [ "$DAYS_SINCE" -ge 7 ]; then
    log "开始模块相似度检测（每7天一次）..."
    python3 ~/ai_memory/merge_modules.py 2>>"$LOG_FILE" &&         log "✅ 模块合并检测完成" ||         log "⚠️  模块合并检测失败（不影响蒸馏结果）"
    date +%s > "$MERGE_FLAG"
else
    log "模块合并检测：距上次检测 ${DAYS_SINCE} 天，下次检测在 $(( 7 - DAYS_SINCE )) 天后"
fi
