#!/bin/bash
# ============================================================
# QQ 邮箱 SMTP 配置向导
# 运行一次，永久生效
# ============================================================

MEMORY_ROOT="$HOME/ai_memory"
CONFIG_FILE="$MEMORY_ROOT/modules/email_config.json"

echo "╔══════════════════════════════════════════════╗"
echo "║     QQ 邮箱 SMTP 配置向导                    ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "需要你的 QQ 邮箱授权码（不是 QQ 密码）"
echo ""
echo "获取授权码步骤："
echo "  1. 打开 QQ 邮箱网页版 (mail.qq.com)"
echo "  2. 设置 → 账户 → POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务"
echo "  3. 开启「SMTP服务」"
echo "  4. 发送短信验证后，会显示一个16位授权码"
echo "  5. 把授权码输入下方"
echo ""
read -p "请输入你的 QQ 邮箱地址（如 164204@qq.com）: " QQ_EMAIL
read -s -p "请输入 SMTP 授权码（输入时不显示）: " SMTP_PASS
echo ""

if [ -z "$QQ_EMAIL" ] || [ -z "$SMTP_PASS" ]; then
    echo "❌ 邮箱或授权码不能为空"
    exit 1
fi

# 保存配置
mkdir -p "$MEMORY_ROOT/modules"
cat > "$CONFIG_FILE" << EOF
{
  "from_email": "$QQ_EMAIL",
  "smtp_pass": "$SMTP_PASS",
  "to_email": "164204@qq.com",
  "smtp_host": "smtp.qq.com",
  "smtp_port": 587,
  "configured_at": "$(date '+%Y-%m-%d %H:%M:%S')"
}
EOF
chmod 600 "$CONFIG_FILE"
echo "✅ 配置已保存到 $CONFIG_FILE（权限已设为仅本用户可读）"

# 测试发送
echo ""
echo "正在发送测试邮件..."
python3 "$MEMORY_ROOT/daily_report.py" && echo "✅ 测试邮件发送成功！请检查 164204@qq.com" || echo "❌ 发送失败，请检查授权码是否正确"

# 注册 LaunchAgent
echo ""
echo "正在注册每日定时任务（09:00 自动发送）..."

PLIST_PATH="$HOME/Library/LaunchAgents/com.ai.daily-report.plist"
cat > "$PLIST_PATH" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ai.daily-report</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>$MEMORY_ROOT/daily_report.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$MEMORY_ROOT/logs/daily_report.log</string>
    <key>StandardErrorPath</key>
    <string>$MEMORY_ROOT/logs/daily_report_err.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
PLIST

launchctl unload "$PLIST_PATH" 2>/dev/null
launchctl load "$PLIST_PATH" && echo "✅ 定时任务注册成功，每天 09:00 自动发送" || echo "❌ 定时任务注册失败"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  配置完成！每天 09:00 你会收到一封邮件       ║"
echo "║  包含：API余额、待办事项、记忆系统状态        ║"
echo "╚══════════════════════════════════════════════╝"
