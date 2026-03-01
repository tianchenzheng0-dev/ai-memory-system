#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TCZ AI 记忆系统 - 腾讯云COS全量备份脚本 v2.0
每天 01:00 自动运行（由 LaunchAgent 触发）

备份范围（全量）：
  - ~/ai_memory/          记忆系统核心（数据+脚本）
  - ~/vertex_proxy/       Gemini代理服务
  - ~/.openclaw/          OpenClaw配置（排除大型缓存）
  - ~/Library/LaunchAgents/com.tcz.* 和 com.manus.*  定时任务
  - pip包列表             requirements.txt（用于恢复时重装）
  - 桌面记忆钥匙

保留策略：保留最近 7 天的备份
"""
import os
import sys
import tarfile
import shutil
import subprocess
import logging
from pathlib import Path
from datetime import datetime, timedelta
from qcloud_cos import CosConfig, CosS3Client

# ── 配置 ──────────────────────────────────────────────
SECRET_ID  = os.environ.get("COS_SECRET_ID", "YOUR_COS_SECRET_ID_HERE")
SECRET_KEY = os.environ.get("COS_SECRET_KEY", "YOUR_COS_SECRET_KEY_HERE")
REGION     = "ap-guangzhou"
BUCKET     = "tcz-ai-memory-backup-1407342633"
KEEP_DAYS  = 7

HOME        = Path.home()
MEMORY_ROOT = HOME / "ai_memory"
DESKTOP     = HOME / "Desktop"
TMP_DIR     = Path("/tmp/ai_memory_backup_v2")
LOG_FILE    = MEMORY_ROOT / "logs" / "backup_cos.log"

# ── 备份目录清单 ──────────────────────────────────────
BACKUP_ITEMS = [
    # (本地路径, 压缩包内名称, 排除规则)
    (MEMORY_ROOT,                    "ai_memory",      ["__pycache__", "*.pyc", ".distill_prompt_tmp.txt"]),
    (HOME / "vertex_proxy",          "vertex_proxy",   []),
    (HOME / ".openclaw",             "openclaw",       [
        "logs", "media", "browser", "canvas",          # 大型缓存目录
        "*.log", "update-check.json",
    ]),
    (HOME / "Library" / "LaunchAgents", "LaunchAgents", []),  # 全部plist
]

# ── 日志 ──────────────────────────────────────────────
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)

def create_client():
    config = CosConfig(Region=REGION, SecretId=SECRET_ID, SecretKey=SECRET_KEY)
    return CosS3Client(config)

def should_exclude(path: Path, excludes: list) -> bool:
    """判断路径是否应该被排除"""
    import fnmatch
    for pattern in excludes:
        if fnmatch.fnmatch(path.name, pattern):
            return True
        if path.name == pattern:
            return True
    return False

def add_dir_to_tar(tar: tarfile.TarFile, src: Path, arcname: str, excludes: list):
    """递归添加目录到tar，支持排除规则"""
    if not src.exists():
        log.warning(f"目录不存在，跳过: {src}")
        return 0
    
    count = 0
    for item in src.rglob("*"):
        # 检查路径中任何部分是否匹配排除规则
        skip = False
        for part in item.parts:
            if should_exclude(Path(part), excludes):
                skip = True
                break
        if skip:
            continue
        
        rel = item.relative_to(src)
        tar_path = f"{arcname}/{rel}"
        try:
            tar.add(str(item), arcname=tar_path, recursive=False)
            count += 1
        except Exception as e:
            log.warning(f"跳过文件 {item}: {e}")
    
    log.info(f"  ✓ {arcname}: {count} 个文件")
    return count

def export_pip_requirements(tmp_dir: Path) -> Path:
    """导出pip包列表"""
    req_file = tmp_dir / "requirements.txt"
    try:
        result = subprocess.run(
            ["pip3", "freeze"],
            capture_output=True, text=True, timeout=30
        )
        req_file.write_text(result.stdout, encoding='utf-8')
        log.info(f"  ✓ pip包列表: {len(result.stdout.splitlines())} 个包")
    except Exception as e:
        req_file.write_text(f"# 导出失败: {e}\n", encoding='utf-8')
        log.warning(f"pip包列表导出失败: {e}")
    return req_file

def export_launchagents_list(tmp_dir: Path) -> Path:
    """导出LaunchAgents状态列表"""
    la_dir = HOME / "Library" / "LaunchAgents"
    list_file = tmp_dir / "launchagents_list.txt"
    
    plists = list(la_dir.glob("com.tcz.*.plist")) + list(la_dir.glob("com.manus.*.plist"))
    lines = [f"# LaunchAgents 备份清单 - {datetime.now().isoformat()}\n"]
    for p in sorted(plists):
        lines.append(f"{p.name}\n")
    
    list_file.write_text("".join(lines), encoding='utf-8')
    log.info(f"  ✓ LaunchAgents清单: {len(plists)} 个")
    return list_file

def make_tarball(date_str: str) -> Path:
    """打包所有备份内容"""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    tmp_files_dir = TMP_DIR / "extras"
    tmp_files_dir.mkdir(exist_ok=True)
    
    tar_path = TMP_DIR / f"tcz_ai_full_backup_{date_str}.tar.gz"
    log.info(f"开始全量打包...")
    
    total = 0
    with tarfile.open(tar_path, "w:gz") as tar:
        # 1. 备份各目录
        for src_path, arcname, excludes in BACKUP_ITEMS:
            if isinstance(src_path, Path) and src_path.exists():
                count = add_dir_to_tar(tar, src_path, arcname, excludes)
                total += count
            else:
                log.warning(f"跳过不存在的路径: {src_path}")
        
        # 2. 只备份 com.tcz.* 和 com.manus.* 的 plist（已在BACKUP_ITEMS里，这里额外确认）
        la_dir = HOME / "Library" / "LaunchAgents"
        for plist in sorted(la_dir.glob("com.tcz.*.plist")) + sorted(la_dir.glob("com.manus.*.plist")):
            try:
                tar.add(str(plist), arcname=f"LaunchAgents/{plist.name}", recursive=False)
            except Exception:
                pass
        
        # 3. pip包列表
        req_file = export_pip_requirements(tmp_files_dir)
        tar.add(str(req_file), arcname="restore_extras/requirements.txt")
        
        # 4. LaunchAgents清单
        la_list = export_launchagents_list(tmp_files_dir)
        tar.add(str(la_list), arcname="restore_extras/launchagents_list.txt")
        
        # 5. 桌面记忆钥匙
        key_file = DESKTOP / "TCZ·AI记忆钥匙_最新.md"
        if key_file.exists():
            tar.add(str(key_file), arcname="TCZ·AI记忆钥匙_最新.md")
            log.info(f"  ✓ 桌面记忆钥匙")
        
        # 6. 写入备份元信息
        meta = {
            "backup_date": date_str,
            "timestamp": datetime.now().isoformat(),
            "hostname": os.uname().nodename,
            "python_version": sys.version,
            "backup_items": [str(item[0]) for item in BACKUP_ITEMS],
            "total_files": total,
            "restore_script": "python3 restore_from_cos.py",
            "restore_deps": "pip3 install cos-python-sdk-v5 chromadb sentence-transformers"
        }
        import json
        meta_file = tmp_files_dir / "backup_meta.json"
        meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
        tar.add(str(meta_file), arcname="restore_extras/backup_meta.json")
    
    size_mb = tar_path.stat().st_size / 1024 / 1024
    log.info(f"打包完成: {tar_path.name} ({size_mb:.2f} MB)，共 {total} 个文件")
    return tar_path

def upload_to_cos(client, local_path: Path, date_str: str):
    cos_key = f"backups/{date_str}/{local_path.name}"
    log.info(f"上传到 COS: {cos_key}")
    with open(local_path, 'rb') as f:
        client.put_object(Bucket=BUCKET, Body=f, Key=cos_key,
                         StorageClass='STANDARD', ContentType='application/gzip')
    with open(local_path, 'rb') as f:
        client.put_object(Bucket=BUCKET, Body=f, Key="backups/latest.tar.gz",
                         StorageClass='STANDARD', ContentType='application/gzip')
    log.info(f"✅ 上传成功: {cos_key}")
    log.info(f"✅ latest 已更新")
    return cos_key

def upload_key_separately(client, date_str: str):
    key_file = DESKTOP / "TCZ·AI记忆钥匙_最新.md"
    if not key_file.exists():
        return
    content = key_file.read_bytes()
    client.put_object(Bucket=BUCKET, Body=content,
                     Key=f"keys/TCZ·AI记忆钥匙_{date_str}.md",
                     ContentType='text/markdown; charset=utf-8')
    client.put_object(Bucket=BUCKET, Body=content,
                     Key="keys/TCZ·AI记忆钥匙_最新.md",
                     ContentType='text/markdown; charset=utf-8')
    log.info(f"✅ 记忆钥匙单独上传完成")

def write_manifest(client, date_str: str, cos_key: str, size_mb: float, file_count: int = 0):
    import json
    manifest = {
        "date": date_str,
        "backup_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "timestamp": datetime.now().isoformat(),
        "file_count": file_count,
        "bucket": BUCKET, "region": REGION,
        "backup_key": cos_key,
        "latest_key": "backups/latest.tar.gz",
        "key_file": "keys/TCZ·AI记忆钥匙_最新.md",
        "size_mb": round(size_mb, 2),
        "backup_scope": ["ai_memory", "vertex_proxy", "openclaw", "LaunchAgents", "pip_packages"],
        "restore_cmd": "python3 restore_from_cos.py",
        "restore_deps": "pip3 install cos-python-sdk-v5"
    }
    content = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')
    client.put_object(Bucket=BUCKET, Body=content, Key="manifest.json",
                     ContentType='application/json')
    log.info("✅ 备份清单已更新")

def cleanup_old_backups(client):
    cutoff = datetime.now() - timedelta(days=KEEP_DAYS)
    try:
        response = client.list_objects(Bucket=BUCKET, Prefix="backups/")
        contents = response.get('Contents', [])
        if isinstance(contents, dict):
            contents = [contents]
        deleted = 0
        for obj in contents:
            key = obj['Key']
            parts = key.split('/')
            if len(parts) >= 2 and len(parts[1]) == 10:
                try:
                    if datetime.strptime(parts[1], "%Y-%m-%d") < cutoff:
                        client.delete_object(Bucket=BUCKET, Key=key)
                        deleted += 1
                except ValueError:
                    pass
        if deleted:
            log.info(f"清理旧备份: {deleted} 个文件")
    except Exception as e:
        log.warning(f"清理旧备份时出错: {e}")

def main():
    date_str = datetime.now().strftime("%Y-%m-%d")
    log.info(f"{'='*55}")
    log.info(f"TCZ AI 全量备份开始: {date_str}")
    log.info(f"目标: COS {BUCKET}")
    
    try:
        client = create_client()
        tar_path = make_tarball(date_str)
        size_mb = tar_path.stat().st_size / 1024 / 1024
        cos_key = upload_to_cos(client, tar_path, date_str)
        upload_key_separately(client, date_str)
        write_manifest(client, date_str, cos_key, size_mb, total)
        cleanup_old_backups(client)
        shutil.rmtree(TMP_DIR, ignore_errors=True)
        log.info(f"{'='*55}")
        log.info(f"✅ 全量备份完成！大小: {size_mb:.2f} MB")
        log.info(f"包含: ai_memory + vertex_proxy + openclaw + LaunchAgents + pip包列表")
    except Exception as e:
        log.error(f"❌ 备份失败: {e}")
        import traceback
        log.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
