#!/bin/bash
# ============================================================
# AI 模型余额查询脚本 v2 - check_balance.sh
# 用法: ./check_balance.sh [--alert]
# --alert 模式：余额低于阈值时发出警告
# ============================================================
source ~/.zshrc 2>/dev/null || true

ALERT_MODE=false
[ "$1" = "--alert" ] && ALERT_MODE=true

TIMESTAMP=$(date "+%Y-%m-%d %H:%M")

echo "=========================================="
echo "  AI 模型余额查询 - $TIMESTAMP"
echo "=========================================="
echo ""

python3 - <<'PYEOF'
import urllib.request, json, os

results = []

def query(name, url, headers, parse_fn):
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            balance, currency = parse_fn(data)
            return {"name": name, "balance": balance, "currency": currency, "status": "ok"}
    except Exception as e:
        return {"name": name, "balance": None, "currency": None, "status": f"失败: {str(e)[:60]}"}

# ---- OpenRouter ----
OPENROUTER_KEY = os.environ.get('OPENROUTER_API_KEY', '')
if OPENROUTER_KEY:
    r = query(
        "OpenRouter",
        "https://openrouter.ai/api/v1/auth/key",
        {"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
        lambda d: (
            f"${d.get('data', {}).get('limit_remaining', '未知')}" 
            if d.get('data', {}).get('limit_remaining') is not None 
            else "无限额度",
            'USD'
        )
    )
    results.append(r)
else:
    results.append({"name": "OpenRouter", "balance": None, "status": "未配置API Key (OPENROUTER_API_KEY)"})

# ---- OpenAI ----
OPENAI_KEY = os.environ.get('OPENAI_API_KEY', '')
if OPENAI_KEY:
    try:
        req = urllib.request.Request(
            "https://api.openai.com/v1/dashboard/billing/credit_grants",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            total = data.get('total_available', 0)
            results.append({"name": "OpenAI", "balance": f"${total:.2f}", "currency": "USD", "status": "ok"})
    except Exception as e:
        results.append({"name": "OpenAI", "balance": None, "status": f"失败: {str(e)[:60]}"})
else:
    results.append({"name": "OpenAI", "balance": None, "status": "未配置API Key (OPENAI_API_KEY)"})

# ---- Kimi (Moonshot) ----
KIMI_KEY = "sk-w80lJYxOgqz3QCVuc62WqHCmaDUzqDfaCEttahi3xQJyz1IV"
try:
    req = urllib.request.Request(
        "https://api.moonshot.cn/v1/users/me/balance",
        headers={"Authorization": f"Bearer {KIMI_KEY}"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
        balance = data.get('data', {}).get('available_balance', '未知')
        results.append({"name": "Kimi (Moonshot)", "balance": f"¥{balance}", "currency": "CNY", "status": "ok"})
except Exception as e:
    results.append({"name": "Kimi (Moonshot)", "balance": None, "status": f"失败: {str(e)[:60]}"})

# ---- 智谱 AI (BigModel / GLM-4) ----
ZHIPU_KEY = "d71126ba8bc74675a0bc99ee38b3a0b9.EoxCaJsYR5in9XxX"
try:
    req = urllib.request.Request(
        "https://open.bigmodel.cn/api/paas/v4/users/me/balance",
        headers={"Authorization": f"Bearer {ZHIPU_KEY}"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
        # 智谱API余额字段
        balance = data.get('data', {}).get('balance', data.get('balance', '未知'))
        results.append({"name": "智谱 AI (GLM-4)", "balance": f"¥{balance}", "currency": "CNY", "status": "ok"})
except Exception as e:
    # 智谱AI可能不提供余额API，直接标注
    results.append({"name": "智谱 AI (GLM-4)", "balance": "需登录控制台查看", "currency": "CNY", "status": "ok"})

# ---- Anthropic ----
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
if ANTHROPIC_KEY:
    results.append({"name": "Anthropic (Claude)", "balance": "需登录控制台查看", "status": "ok"})
else:
    results.append({"name": "Anthropic (Claude)", "balance": None, "status": "未配置API Key (ANTHROPIC_API_KEY)"})

# ---- Groq ----
GROQ_KEY = os.environ.get('GROQ_API_KEY', '')
if GROQ_KEY:
    results.append({"name": "Groq (Llama3)", "balance": "免费额度，无需查询", "status": "ok"})
else:
    results.append({"name": "Groq (Llama3)", "balance": None, "status": "未配置API Key (GROQ_API_KEY)"})

# ---- 输出结果 ----
LOW_THRESHOLD_USD = 5
LOW_THRESHOLD_CNY = 35
warnings = []

for r in results:
    name = r['name']
    status = r['status']
    balance = r.get('balance')
    currency = r.get('currency', '')
    
    if status == 'ok' and balance is not None:
        print(f"  ✅ {name:<25} {balance}")
        # 检查低余额
        try:
            num = float(str(balance).replace('$', '').replace('¥', '').replace(',', ''))
            threshold = LOW_THRESHOLD_CNY if currency == 'CNY' else LOW_THRESHOLD_USD
            unit = '¥' if currency == 'CNY' else '$'
            if num < threshold:
                warnings.append(f"⚠️  {name} 余额不足 ({balance})，请及时充值！")
        except:
            pass
    else:
        print(f"  ❌ {name:<25} {status}")

print("")
if warnings:
    print("========== ⚠️  余额预警 ==========")
    for w in warnings:
        print(f"  {w}")
    print("")
else:
    print("  ✅ 所有已配置的模型余额充足")
    print("")

PYEOF

echo "=========================================="
echo "控制台地址："
echo "  OpenRouter: https://openrouter.ai/credits"
echo "  OpenAI:     https://platform.openai.com/usage"
echo "  Kimi:       https://platform.moonshot.cn/console"
echo "  智谱AI:     https://open.bigmodel.cn/usercenter/overview"
echo "  Anthropic:  https://console.anthropic.com/settings/billing"
echo "  Groq:       https://console.groq.com"
echo "=========================================="
