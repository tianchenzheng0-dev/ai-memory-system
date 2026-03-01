#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TCZ AI 记忆系统 - 从腾讯云COS全量恢复脚本 v2.0

使用方法：
  python3 restore_from_cos.py              # 恢复最新备份（交互确认）
  python3 restore_from_cos.py --auto       # 全自动恢复（无需确认）
  python3 restore_from_cos.py --list       # 列出所有可用备份
  python3 restore_from_cos.py --key-only   # 只下载记忆钥匙

恢复内容：
  ✅ ~/ai_memory/          记忆系统核心
  ✅ ~/vertex_proxy/       Gemini代理
  ✅ ~/.openclaw/          OpenClaw配置
  ✅ LaunchAgents          定时任务（自动注册）
  ✅ pip 依赖              自动重装
  ✅ 桌面记忆钥匙          自动放回桌面
"""
import os, sys, tarfile, json, shutil, subprocess
from pathlib import Path
from datetime import datetime

# ── 安装基础依赖 ──────────────────────────────────────
try:
    from qcloud_cos import CosConfig, CosS3Client
except ImportError:
    print("正在安装腾讯云SDK...")
    subprocess.run([sys.executable, "-m", "pip", "install", "cos-python-sdk-v5", "-q"])
    from qcloud_cos import CosConfig, CosS3Client

# ── 配置 ──────────────────────────────────────────────
SECRET_ID  = os.environ.get("COS_SECRET_ID", "YOUR_COS_SECRET_ID_HERE")
SECRET_KEY = os.environ.get("COS_SECRET_KEY", "YOUR_COS_SECRET_KEY_HERE")
REGION     = "ap-guangzhou"
BUCKET     = "tcz-ai-memory-backup-1407342633"

HOME      = Path.home()
TMP_DIR   = Path("/tmp/tcz_ai_restore")

def create_client():
    config = CosConfig(Region=REGION, SecretId=SECRET_ID, SecretKey=SECRET_KEY)
    return CosS3Client(config)

def print_step(n, text):
    print(f"\n{'─'*50}")
    print(f"  步骤 {n}：{text}")
    print(f"{'─'*50}")

def download_file(client, cos_key: str, local_path: Path):
    local_path.parent.mkdir(parents=True, exist_ok=True)
    response = client.get_object(Bucket=BUCKET, Key=cos_key)
    response['Body'].get_stream_to_file(str(local_path))

def list_backups(client):
    response = client.list_objects(Bucket=BUCKET, Prefix="backups/", Delimiter="/")
    prefixes = response.get('CommonPrefixes', [])
    if isinstance(prefixes, dict):
        prefixes = [prefixes]
    dates = [p.get('Prefix','').replace('backups/','').rstrip('/') for p in prefixes if len(p.get('Prefix','').replace('backups/','').rstrip('/')) == 10]
    return sorted(dates, reverse=True)

def get_manifest(client):
    try:
        resp = client.get_object(Bucket=BUCKET, Key="manifest.json")
        return json.loads(resp['Body'].get_raw_stream().read().decode('utf-8'))
    except:
        return None

def step_download(client, date_str=None):
    """步骤1：下载备份包"""
    print_step(1, "从腾讯云COS下载备份包")
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    
    cos_key = f"backups/{date_str}/{date_str}.tar.gz" if date_str else "backups/latest.tar.gz"
    # 尝试新格式和旧格式
    tar_path = TMP_DIR / "backup.tar.gz"
    
    print(f"  下载: {cos_key}")
    try:
        download_file(client, cos_key, tar_path)
    except Exception:
        # 尝试新命名格式
        if date_str:
            cos_key2 = f"backups/{date_str}/tcz_ai_full_backup_{date_str}.tar.gz"
            print(f"  尝试: {cos_key2}")
            download_file(client, cos_key2, tar_path)
        else:
            raise
    
    size_mb = tar_path.stat().st_size / 1024 / 1024
    print(f"  ✅ 下载完成，大小: {size_mb:.2f} MB")
    return tar_path

def step_backup_existing():
    """步骤2：备份现有文件（如果存在）"""
    print_step(2, "备份现有文件（防止覆盖）")
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backed_up = []
    
    for target in ["ai_memory", "vertex_proxy"]:
        existing = HOME / target
        if existing.exists():
            backup_path = HOME / f"{target}_before_restore_{ts}"
            shutil.move(str(existing), str(backup_path))
            backed_up.append(str(backup_path))
            print(f"  ✅ 已备份: {existing} → {backup_path.name}")
    
    if not backed_up:
        print("  （无现有文件需要备份）")
    return backed_up

def step_extract(tar_path: Path):
    """步骤3：解压还原"""
    print_step(3, "解压还原所有文件")
    
    with tarfile.open(tar_path, "r:gz") as tar:
        members = tar.getmembers()
        print(f"  共 {len(members)} 个文件")
        
        for member in members:
            name = member.name
            
            # ai_memory → ~/ai_memory/
            if name.startswith("ai_memory/"):
                member.name = name  # 保持原路径
                tar.extract(member, path=str(HOME))
            
            # vertex_proxy → ~/vertex_proxy/
            elif name.startswith("vertex_proxy/"):
                tar.extract(member, path=str(HOME))
            
            # openclaw → ~/.openclaw/
            elif name.startswith("openclaw/"):
                member.name = ".openclaw/" + name[len("openclaw/"):]
                tar.extract(member, path=str(HOME))
            
            # LaunchAgents → ~/Library/LaunchAgents/
            elif name.startswith("LaunchAgents/"):
                la_dir = HOME / "Library" / "LaunchAgents"
                la_dir.mkdir(parents=True, exist_ok=True)
                member.name = name[len("LaunchAgents/"):]
                if member.name:
                    tar.extract(member, path=str(la_dir))
            
            # 桌面钥匙
            elif name == "TCZ·AI记忆钥匙_最新.md":
                desktop = HOME / "Desktop"
                desktop.mkdir(exist_ok=True)
                member.name = name
                tar.extract(member, path=str(desktop))
                print(f"  ✅ 记忆钥匙已放回桌面")
    
    print(f"  ✅ 解压完成")

def step_install_deps():
    """步骤4：自动安装pip依赖"""
    print_step(4, "自动安装Python依赖包")
    
    req_file = HOME / "ai_memory" / "restore_extras" / "requirements.txt"
    
    # 必装的核心依赖
    core_deps = [
        "cos-python-sdk-v5",
        "chromadb",
        "sentence-transformers",
        "requests",
    ]
    
    print("  安装核心依赖...")
    for dep in core_deps:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", dep, "-q"],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                print(f"  ✅ {dep}")
            else:
                print(f"  ⚠️  {dep} 安装失败（非致命）")
        except Exception as e:
            print(f"  ⚠️  {dep}: {e}")
    
    # 如果有完整requirements.txt，也安装
    if req_file.exists():
        print("\n  从备份的requirements.txt安装其他依赖...")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(req_file), "-q",
                 "--no-deps"],  # 不递归安装依赖，避免版本冲突
                timeout=300
            )
            print("  ✅ requirements.txt 安装完成")
        except Exception as e:
            print(f"  ⚠️  requirements.txt 安装部分失败: {e}")

def step_register_launchagents():
    """步骤5：注册LaunchAgents定时任务"""
    print_step(5, "注册定时任务（LaunchAgents）")
    
    la_dir = HOME / "Library" / "LaunchAgents"
    plists = list(la_dir.glob("com.tcz.*.plist")) + list(la_dir.glob("com.manus.*.plist"))
    
    if not plists:
        print("  （无LaunchAgents需要注册）")
        return
    
    registered = 0
    for plist in sorted(plists):
        try:
            # 先卸载（忽略错误）
            subprocess.run(["launchctl", "unload", str(plist)],
                          capture_output=True, timeout=5)
            # 重新加载
            result = subprocess.run(["launchctl", "load", str(plist)],
                                   capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print(f"  ✅ {plist.name}")
                registered += 1
            else:
                print(f"  ⚠️  {plist.name}: {result.stderr.strip()}")
        except Exception as e:
            print(f"  ⚠️  {plist.name}: {e}")
    
    print(f"\n  共注册 {registered}/{len(plists)} 个定时任务")

def step_verify():
    """步骤6：验证恢复结果"""
    print_step(6, "验证恢复结果")
    
    checks = [
        (HOME / "ai_memory" / "core1.md",           "核心记忆 core1.md"),
        (HOME / "ai_memory" / "ai_start.sh",         "启动脚本 ai_start.sh"),
        (HOME / "ai_memory" / "distill.sh",           "蒸馏脚本 distill.sh"),
        (HOME / "vertex_proxy" / "proxy.py",          "Gemini代理 proxy.py"),
        (HOME / ".openclaw" / "openclaw.json",         "OpenClaw配置"),
        (HOME / "Desktop" / "TCZ·AI记忆钥匙_最新.md", "桌面记忆钥匙"),
    ]
    
    ok = 0
    for path, name in checks:
        if path.exists():
            print(f"  ✅ {name}")
            ok += 1
        else:
            print(f"  ❌ {name} — 未找到")
    
    return ok, len(checks)

def download_key_only(client):
    """只下载记忆钥匙"""
    print("下载最新记忆钥匙...")
    local_path = HOME / "Desktop" / "TCZ·AI记忆钥匙_最新.md"
    try:
        download_file(client, "keys/TCZ·AI记忆钥匙_最新.md", local_path)
        print(f"✅ 记忆钥匙已下载到桌面: {local_path}")
    except Exception as e:
        print(f"❌ 下载失败: {e}")

def main():
    args = sys.argv[1:]
    auto_mode = "--auto" in args
    
    print("=" * 55)
    print("  TCZ AI 记忆系统 — 全量恢复工具 v2.0")
    print(f"  COS: {BUCKET}")
    print("=" * 55)
    
    client = create_client()
    print("✅ 腾讯云连接成功")
    
    if "--list" in args:
        dates = list_backups(client)
        manifest = get_manifest(client)
        print(f"\n可用备份（共 {len(dates)} 个）:")
        for d in dates:
            print(f"  {d}")
        if manifest:
            print(f"\n最新备份: {manifest['date']} ({manifest.get('size_mb','?')} MB)")
            print(f"备份范围: {', '.join(manifest.get('backup_scope', []))}")
        return
    
    if "--key-only" in args:
        download_key_only(client)
        return
    
    # 确定恢复日期
    date_str = None
    for arg in args:
        if len(arg) == 10 and arg[4] == '-':
            date_str = arg
    
    # 显示备份信息
    manifest = get_manifest(client)
    if manifest:
        print(f"\n最新备份信息:")
        print(f"  日期: {manifest['date']}")
        print(f"  大小: {manifest.get('size_mb','?')} MB")
        print(f"  备份范围: {', '.join(manifest.get('backup_scope', []))}")
    
    # 确认
    if not auto_mode:
        target = date_str if date_str else "最新"
        confirm = input(f"\n确认恢复 [{target}] 备份？这将覆盖现有文件。(y/n): ").strip().lower()
        if confirm != 'y':
            print("已取消")
            return
    
    # 执行恢复
    try:
        tar_path = step_download(client, date_str)
        step_backup_existing()
        step_extract(tar_path)
        step_install_deps()
        step_register_launchagents()
        ok, total = step_verify()
        
        # 清理临时文件
        shutil.rmtree(TMP_DIR, ignore_errors=True)
        
        print(f"\n{'='*55}")
        print(f"  ✅ 恢复完成！验证通过 {ok}/{total} 项")
        print(f"{'='*55}")
        print("\n下一步：")
        print("  加载记忆: bash ~/ai_memory/ai_start.sh")
        print("  测试Gemini代理: curl http://127.0.0.1:11435/v1/models")
        
        if ok < total:
            print(f"\n⚠️  有 {total-ok} 项未找到，可能需要手动检查")
    
    except Exception as e:
        print(f"\n❌ 恢复失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
