import argparse
import time
import re
import yaml
from pathlib import Path
from datetime import datetime

# -----------------------------------------------------------------
# 配置
# -----------------------------------------------------------------

# 显式地将项目根目录添加到 Python 路径中
PROJECT_ROOT = Path(__file__).resolve().parent

# 1. 要清理的目录 (相对于本项目根目录)
TARGET_DIRS_RELATIVE = [
    "data",
]

# 2. (V4 更新) 增强型正则表达式
# 兼容旧版: _1762871926 (10位数字)
# 兼容新版: _20251128T171645Z (ISO 格式)
TIMESTAMP_RE = re.compile(r"_(\d{10}|\d{8}T\d{6}Z)$")


# -----------------------------------------------------------------
# 辅助: 从 symbols.yaml 解析出 manual_only 的标的集合
# -----------------------------------------------------------------

def load_manual_only_symbols() -> set:
    """读 symbols.yaml, 返回 runnable=false 的 symbol 集合 (大写).
    这些是 Claude Code 手动分析的标的, 默认保护它们的缓存不被清."""
    cfg_path = PROJECT_ROOT / "config" / "symbols.yaml"
    if not cfg_path.exists():
        return set()
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding='utf-8')) or {}
    except Exception as e:
        print(f"[警告] 读 symbols.yaml 失败: {e}, 默认 manual_only 集合为空")
        return set()
    manual = set()
    for sym, info in (cfg.get('symbol_contracts') or {}).items():
        if isinstance(info, dict) and info.get('runnable') is False:
            manual.add(str(sym).upper())
    return manual


def path_belongs_to_manual_symbol(file_path: Path, manual_set: set) -> str:
    """若文件路径的任一目录段匹配 manual symbol, 返回该 symbol; 否则返回空字符串.
    例: data/news/RHM/RHM_news_xxx.json 命中 RHM."""
    for part in file_path.parts:
        if part.upper() in manual_set:
            return part.upper()
    return ""

# -----------------------------------------------------------------
# 主逻辑
# -----------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Apex Quant 缓存清理工具 (V4 兼容版)",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="保留期限（天）。\n文件时间戳早于 N 天前的将被删除。\n(默认: 7)"
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="!!! 危险 !!! 实际执行删除操作。\n(默认: 'Dry Run'，只打印不删除)"
    )
    parser.add_argument(
        "--include-manual",
        action="store_true",
        help="同时清理 manual_only 标的 (RHM/7974/7011 等 runnable=false 的) 的缓存。\n"
             "(默认: 跳过, 保护 Claude Code 手动分析的数据不被清掉)"
    )
    args = parser.parse_args()

    # --- 1.5 加载 manual_only 集合用于过滤 ---
    manual_symbols = set() if args.include_manual else load_manual_only_symbols()
    if manual_symbols:
        print(f"[保护] 跳过 manual_only 标的的缓存: {sorted(manual_symbols)}")
        print(f"        (要也清, 加 --include-manual 参数)")
    elif args.include_manual:
        print("[模式] --include-manual: 包含 manual_only 标的, 全部清理")

    # --- 1. 计算时间 ---
    NOW_TS = time.time()
    CUTOFF_SECONDS = args.days * 24 * 60 * 60
    CUTOFF_TIMESTAMP = NOW_TS - CUTOFF_SECONDS
    cutoff_dt = datetime.fromtimestamp(CUTOFF_TIMESTAMP)

    if args.run:
        print("="*60)
        print("!!! 模式: DELETION RUN (正在永久删除文件) !!!")
        print("="*60)
    else:
        print("="*60)
        print("--- 模式: DRY RUN (仅报告，不删除) ---")
        print("--- (如需删除，请使用 --run 参数) ---")
        print("="*60)

    print(f"保留期限: {args.days} 天")
    print(f"清理标准: 删除时间戳早于 {cutoff_dt.strftime('%Y-%m-%d %H:%M:%S')} 的文件")

    # --- 2. 转换路径为绝对路径 ---
    target_dirs_absolute = [PROJECT_ROOT / p for p in TARGET_DIRS_RELATIVE]

    total_scanned = 0
    total_found_expired = 0
    total_deleted = 0
    total_skipped_manual = 0

    # --- 3. 扫描和清理 ---
    for target_dir in target_dirs_absolute:
        # 计算相对路径用于显示
        try:
            display_path = target_dir.relative_to(PROJECT_ROOT)
        except ValueError:
            display_path = target_dir

        print(f"\n--- 正在扫描: {display_path} ---")
        if not target_dir.exists():
            print(f"  [警告] 目录不存在，已跳过。")
            continue

        for file_path in target_dir.rglob('*'):
            if not file_path.is_file():
                continue

            total_scanned += 1

            # manual_only 标的的缓存保护 (除非用户显式 --include-manual)
            if manual_symbols:
                hit_sym = path_belongs_to_manual_symbol(file_path, manual_symbols)
                if hit_sym:
                    total_skipped_manual += 1
                    continue

            # 从文件名中提取时间戳
            stem = file_path.stem
            match = TIMESTAMP_RE.search(stem)

            if not match:
                continue

            ts_str = match.group(1)
            file_timestamp = 0

            try:
                if "T" in ts_str:
                    # 解析新格式: 20251128T171645Z
                    dt = datetime.strptime(ts_str, "%Y%m%dT%H%M%SZ")
                    file_timestamp = dt.timestamp()
                else:
                    # 解析旧格式: 1762871926
                    file_timestamp = float(ts_str)
            except Exception:
                continue

            # 4. 对比时间
            if file_timestamp < CUTOFF_TIMESTAMP:
                total_found_expired += 1
                try:
                    file_age_days = (NOW_TS - file_timestamp) / 86400
                    status = "[删除]" if args.run else "[发现过期]"
                    print(f"  {status} {file_path.name} ({file_age_days:.1f} 天前)")
                    
                    if args.run:
                        file_path.unlink()
                        total_deleted += 1
                        
                except Exception as e:
                    print(f"    [错误] 无法处理 {file_path.name}: {e}")

    # --- 5. 总结 ---
    print("\n" + "="*60)
    print("--- 清理完成 ---")
    print(f"总共扫描文件数: {total_scanned}")
    if manual_symbols:
        print(f"manual_only 跳过文件数: {total_skipped_manual} (--include-manual 可一并清)")
    print(f"发现过期文件数: {total_found_expired}")
    print(f"实际删除文件数: {total_deleted}")
    print("="*60)
    
    if not args.run and total_found_expired > 0:
        print(f"\n(提示) 这是 Dry Run。要实际删除这 {total_found_expired} 个文件，请再次运行并添加 --run 参数。")


if __name__ == "__main__":
    main()