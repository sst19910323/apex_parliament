#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apex_quant_entry.py - Apex Quant Backend (V13.3 - Strict V13 Only)
核心修正:
1. [Strict Mode] _extract_core_signal: 仅支持最新的扁平化 JSON 结构。
   不再尝试读取 final_report 嵌套字段，强制要求前端/AI生成符合新标准。
2. Dashboard: 聚合所有标的最新状态。
"""

import json
import yaml
import uvicorn
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# --- 初始化 ---
app = FastAPI(title="Apex Quant API V13", version="13.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 路径配置 ---
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_CACHE_DIR = PROJECT_ROOT / "data"
CONFIG_SYMBOLS = PROJECT_ROOT / "config" / "symbols.yaml"
CONFIG_DATA = PROJECT_ROOT / "config" / "data_sources.yaml"

def get_results_dir() -> Path:
    """动态获取结果目录，失败则回退到默认"""
    default_path = PROJECT_ROOT / "results" / "debate"
    if not CONFIG_DATA.exists(): return default_path
    try:
        with open(CONFIG_DATA, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
            rel = cfg.get("data_sources", {}).get("ai_analysis", {}).get("output_dir")
            if rel: return (PROJECT_ROOT / rel).resolve()
    except: pass
    return default_path

RESULTS_DIR = get_results_dir()
print(f"📂 API Serving Results from: {RESULTS_DIR}")

# --- 宏观标的列表 (按 symbols.yaml `analysis_targets.generals` 配置) ---
# GENERAL 系列以 symbols.yaml 为 SoT, 三个内置: GENERAL (US) / GENERAL_EU / GENERAL_JP
# 每个虚拟标的在 symbol_contracts 里有 region + currency + runnable 声明。

def list_general_symbols() -> List[Dict[str, Any]]:
    """读 symbols.yaml 的 GENERAL 系列, 返回前端 item 列表 (含 region/currency/manual_only)."""
    fallback = [{"symbol": "GENERAL", "type": "general", "currency": "USD", "region": "US"}]
    if not CONFIG_SYMBOLS.exists():
        return fallback
    try:
        with open(CONFIG_SYMBOLS, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"❌ Error reading symbols config for generals: {e}")
        return fallback

    targets = cfg.get('analysis_targets', {}) or {}
    contracts = cfg.get('symbol_contracts', {}) or {}
    generals = targets.get('generals') or ["GENERAL"]

    region_curr_default = {"US": "USD", "EU": "EUR", "JP": "JPY"}
    out: List[Dict[str, Any]] = []
    for sym in generals:
        sym_u = str(sym).upper()
        info = contracts.get(sym_u, {}) or {}
        region = (info.get('region') or "US").upper()
        item: Dict[str, Any] = {
            "symbol": sym_u,
            "type": "general",
            "currency": info.get('currency') or region_curr_default.get(region, "USD"),
            "region": region,
        }
        if info.get('runnable') is False:
            item["manual_only"] = True
        out.append(item)
    return out or fallback

# --- 辅助: 路径安全检查 ---
def safe_path(rel_path: str) -> Path:
    try:
        clean_path = Path(rel_path.lstrip("/\\"))
        abs_path = (PROJECT_ROOT / clean_path).resolve()
        # 严格限制在项目根目录下
        if not str(abs_path).startswith(str(PROJECT_ROOT)):
            raise ValueError
        return abs_path
    except:
        raise HTTPException(status_code=403, detail="Invalid path or access denied")

# =================================================================
# 核心业务接口
# =================================================================

# --- API 1: 获取标的列表 (带类型) ---
@app.get("/api/symbols", tags=["Core"])
def get_symbols() -> List[Dict[str, str]]:
    """
    返回: [{"symbol": "AAPL", "type": "stock"}, ...]
    """
    result_list = []

    # 1. GENERAL 系列永远置顶 (按 symbols.yaml generals 列表)
    for gi in list_general_symbols():
        result_list.append({"symbol": gi["symbol"], "type": "general"})

    # 2. 读取配置
    if CONFIG_SYMBOLS.exists():
        try:
            with open(CONFIG_SYMBOLS, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}
                targets = cfg.get('analysis_targets', {})
                
                # Stocks
                for s in targets.get('stocks', []):
                    result_list.append({"symbol": s.upper(), "type": "stock"})
                
                # ETFs
                for s in targets.get('etfs', []):
                    result_list.append({"symbol": s.upper(), "type": "etf"})
        except Exception as e:
            print(f"❌ Error reading symbols config: {e}")

    return result_list

# --- API 1b: 按板块/层级分组的标的列表 (前端按组渲染用) ---
@app.get("/api/symbol-groups", tags=["Core"])
def get_symbol_groups() -> List[Dict[str, Any]]:
    """
    返回按层级/板块分组的标的列表，前端可直接铺成分组行。

    顺序:
      1. 宏观                            (GENERAL)
      2. 综合 / 宽基                     (benchmark=null 的 ETF: SPY/QQQ/GLD)
      3. 各板块组 (按 yaml display_group) (板块 ETF + 该板块的成员个股)
      4. 大盘核心 (无板块)               (无 sector 字段的个股)

    返回结构:
      [
        {"group": "半导体", "items": [{"symbol":"SMH","type":"etf"},
                                       {"symbol":"NVDA","type":"stock"}, ...]},
        ...
      ]
    """
    groups: List[Dict[str, Any]] = []

    # 1. 宏观永远置顶 (含所有 GENERAL 系列, 按 symbols.yaml generals 列表)
    groups.append({
        "group": "宏观",
        "items": [{"symbol": gi["symbol"], "type": "general"} for gi in list_general_symbols()]
    })

    if not CONFIG_SYMBOLS.exists():
        return groups

    try:
        with open(CONFIG_SYMBOLS, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"❌ Error reading symbols config: {e}")
        return groups

    targets = cfg.get('analysis_targets', {})
    contracts = cfg.get('symbol_contracts', {})

    stock_list = [s.upper() for s in (targets.get('stocks') or [])]
    etf_list = [s.upper() for s in (targets.get('etfs') or [])]

    def _item(sym: str, ctype: str) -> Dict[str, Any]:
        """构造前端 item; 暴露 currency/region (默认 USD/US); runnable=false 标 manual_only=true."""
        info = contracts.get(sym, {}) or {}
        item: Dict[str, Any] = {
            "symbol":   sym,
            "type":     ctype,
            "currency": info.get('currency') or "USD",   # 默认 USD; RHM=EUR; 日股=JPY
            "region":   info.get('region') or "US",      # 默认 US; RHM=EU; 7974/7011=JP
        }
        if info.get('runnable') is False:
            item["manual_only"] = True
        return item

    # 区分宽基 ETF (benchmark=null) 与 板块 ETF (有 benchmark)
    broad_etfs: List[str] = []
    sector_etfs: List[Tuple[str, str]] = []  # [(display_group, etf_symbol), ...]
    for etf in etf_list:
        info = contracts.get(etf, {}) or {}
        if info.get('benchmark') is None:
            broad_etfs.append(etf)
        else:
            display = info.get('display_group') or etf
            sector_etfs.append((display, etf))

    # 2. 综合 / 宽基
    if broad_etfs:
        groups.append({
            "group": "综合 / 宽基",
            "items": [_item(s, "etf") for s in broad_etfs]
        })

    # 先一次性把所有个股按归属分桶: 有 sector 的进 sector_to_stocks, 否则按 display_group 进 custom_groups, 都没就 truly_orphan
    sector_to_stocks: Dict[str, List[str]] = {etf: [] for _, etf in sector_etfs}
    custom_groups: Dict[str, List[str]] = {}
    truly_orphan: List[str] = []
    for stock in stock_list:
        info = contracts.get(stock, {}) or {}
        sector = info.get('sector')
        if sector and sector in sector_to_stocks:
            sector_to_stocks[sector].append(stock)
            continue
        dg = info.get('display_group')
        if dg:
            custom_groups.setdefault(dg, []).append(stock)
        else:
            truly_orphan.append(stock)

    # 3. 自定义组 (Mag7 等无 sector 但有 display_group 的) — 紧跟宽基之后, 排在板块之前
    for dg_name, members in custom_groups.items():
        groups.append({
            "group": dg_name,
            "items": [_item(s, "stock") for s in members]
        })

    # 4. 板块组
    for display, etf in sector_etfs:
        items: List[Dict[str, Any]] = [_item(etf, "etf")]
        for stock in sector_to_stocks.get(etf, []):
            items.append(_item(stock, "stock"))
        groups.append({"group": display, "items": items})

    # 5. 其它 (无 sector 也无 display_group)
    if truly_orphan:
        groups.append({
            "group": "其它",
            "items": [_item(s, "stock") for s in truly_orphan]
        })

    return groups

# --- API 1c: 三级树 (大区 → 板块/分组 → 个股) ---
@app.get("/api/symbol-tree", tags=["Core"])
def get_symbol_tree() -> List[Dict[str, Any]]:
    """
    返回三级嵌套: 大区 → 板块/分组 → 个股

    结构:
      [
        {
          "region": "US",
          "region_label": "美国",
          "groups": [
            {"group": "宏观",        "items": [{"symbol":"GENERAL", ...}]},
            {"group": "综合 / 宽基",  "items": [...]},
            {"group": "Mag7",        "items": [...]},
            {"group": "半导体",       "items": [{"symbol":"SMH",...}, {"symbol":"NVDA",...}]},
            ...
          ]
        },
        {
          "region": "EU", "region_label": "欧洲",
          "groups": [
            {"group": "国防航天", "items": [{"symbol":"RHM", "manual_only":true, ...}]}
          ]
        },
        {
          "region": "JP", "region_label": "日本",
          "groups": [
            {"group": "其它", "items": [{"symbol":"7974",...}, {"symbol":"7011",...}]}
          ]
        }
      ]

    说明:
      - 区 (region) 来自 symbol_contracts.{sym}.region, 缺省 = US
      - 大区内分组逻辑跟 /api/symbol-groups 相同: 宏观 → 宽基 → 自定义组 → 板块组 → 其它
      - 板块 ETF (如 ITA) 永远属于 US 大区; 非 US 标的若 sector 指向某 US 板块 ETF (如 RHM→ITA),
        在非 US 大区内仅展示该板块的标的, 不带 ETF leader
      - GENERAL 系列按 symbols.yaml `analysis_targets.generals` 配置, 当前: GENERAL (US) / GENERAL_EU / GENERAL_JP, 各落到自己 region
    """
    REGION_LABELS = {"US": "美国", "EU": "欧洲", "JP": "日本"}
    REGION_ORDER = ["US", "EU", "JP"]

    if not CONFIG_SYMBOLS.exists():
        return []

    try:
        with open(CONFIG_SYMBOLS, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"❌ Error reading symbols config: {e}")
        return []

    targets = cfg.get('analysis_targets', {})
    contracts = cfg.get('symbol_contracts', {})
    stock_list = [s.upper() for s in (targets.get('stocks') or [])]
    etf_list = [s.upper() for s in (targets.get('etfs') or [])]

    def _item(sym: str, ctype: str) -> Dict[str, Any]:
        info = contracts.get(sym, {}) or {}
        item: Dict[str, Any] = {
            "symbol":   sym,
            "type":     ctype,
            "currency": info.get('currency') or "USD",
            "region":   info.get('region') or "US",
        }
        if info.get('runnable') is False:
            item["manual_only"] = True
        return item

    # region → list of groups
    region_groups: Dict[str, List[Dict[str, Any]]] = {r: [] for r in REGION_ORDER}

    # 1. 宏观 (GENERAL 系列) — 按 region 落到对应大区, 来源 symbols.yaml `analysis_targets.generals`
    for gi in list_general_symbols():
        region = gi.get("region", "US")
        if region not in region_groups:
            region = "US"  # 未知 region 兜底进 US
        region_groups[region].append({
            "group": "宏观",
            "items": [gi]
        })

    # 区分宽基 vs 板块 ETF (现状所有 ETF 都是 US)
    broad_etfs: List[str] = []
    sector_etfs: List[Tuple[str, str]] = []   # [(display_group, etf_symbol), ...]
    for etf in etf_list:
        info = contracts.get(etf, {}) or {}
        if info.get('benchmark') is None:
            broad_etfs.append(etf)
        else:
            display = info.get('display_group') or etf
            sector_etfs.append((display, etf))

    # 2. 综合 / 宽基 (US)
    if broad_etfs:
        region_groups["US"].append({
            "group": "综合 / 宽基",
            "items": [_item(s, "etf") for s in broad_etfs]
        })

    # 个股按 region 拆桶
    per_region_sector: Dict[str, Dict[str, List[str]]] = {
        r: {etf: [] for _, etf in sector_etfs} for r in REGION_ORDER
    }
    per_region_custom: Dict[str, Dict[str, List[str]]] = {r: {} for r in REGION_ORDER}
    per_region_orphan: Dict[str, List[str]] = {r: [] for r in REGION_ORDER}

    for stock in stock_list:
        info = contracts.get(stock, {}) or {}
        region = info.get('region') or "US"
        if region not in per_region_sector:
            region = "US"      # 未知 region 兜底进 US
        sector = info.get('sector')
        if sector and sector in per_region_sector[region]:
            per_region_sector[region][sector].append(stock)
            continue
        dg = info.get('display_group')
        if dg:
            per_region_custom[region].setdefault(dg, []).append(stock)
        else:
            per_region_orphan[region].append(stock)

    # 3+4+5: 在每个 region 内拼装
    for r in REGION_ORDER:
        # 自定义组 (Mag7 等)
        for dg_name, members in per_region_custom[r].items():
            region_groups[r].append({
                "group": dg_name,
                "items": [_item(s, "stock") for s in members]
            })
        # 板块组
        for display, etf in sector_etfs:
            members = per_region_sector[r].get(etf, [])
            if r == "US":
                # US: 板块 ETF leader + 成员个股
                items: List[Dict[str, Any]] = [_item(etf, "etf")]
                items.extend(_item(s, "stock") for s in members)
                region_groups[r].append({"group": display, "items": items})
            elif members:
                # 非 US: 借用 US 板块名作分组标签, 不带 ETF leader
                region_groups[r].append({
                    "group": display,
                    "items": [_item(s, "stock") for s in members]
                })
        # 其它
        if per_region_orphan[r]:
            region_groups[r].append({
                "group": "其它",
                "items": [_item(s, "stock") for s in per_region_orphan[r]]
            })

    # 组装最终输出 (空 region 不返回)
    result: List[Dict[str, Any]] = []
    for r in REGION_ORDER:
        if region_groups[r]:
            result.append({
                "region": r,
                "region_label": REGION_LABELS[r],
                "groups": region_groups[r]
            })
    return result

# --- API 2: 获取历史报告列表 ---
@app.get("/api/reports/{symbol}", tags=["Core"])
def get_symbol_reports(symbol: str) -> List[Dict[str, Any]]:
    """
    返回该标的所有历史报告元数据，按时间倒序。
    """
    target_dir = RESULTS_DIR / symbol.upper()
    if not target_dir.exists(): return []

    files = list(target_dir.glob("*.json"))
    report_list = []
    
    for f in files:
        dt_obj = None
        ts = 0
        try:
            # 文件名解析逻辑: SYMBOL_Analysis_YYYYMMDDTHHMMSSZ.json
            parts = f.stem.split('_')
            candidate = parts[-1]
            
            if "T" in candidate and candidate.endswith("Z"):
                dt_obj = datetime.strptime(candidate, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            elif candidate.isdigit():
                dt_obj = datetime.fromtimestamp(int(candidate), tz=timezone.utc)
            else:
                dt_obj = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                
        except Exception:
            dt_obj = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)

        ts = int(dt_obj.timestamp())
        date_str = dt_obj.strftime('%Y-%m-%d %H:%M:%S UTC')
        rel_path = str(f.relative_to(PROJECT_ROOT)).replace("\\", "/")
        
        report_list.append({
            "filename": f.name,
            "timestamp": ts,
            "date": date_str,
            "path": rel_path
        })
    
    report_list.sort(key=lambda x: x['timestamp'], reverse=True)
    return report_list

# --- API 3: 万能文件读取 ---
@app.get("/api/file", tags=["Core"])
def get_file_content(path: str = Query(..., description="相对路径")) -> Any:
    """
    读取任意 JSON 文件内容。
    """
    abs_path = safe_path(path)
    
    is_data = str(abs_path).startswith(str(DATA_CACHE_DIR))
    is_result = str(abs_path).startswith(str(RESULTS_DIR))
    
    if not (is_data or is_result):
        raise HTTPException(status_code=403, detail="Access denied: Path outside allowed data dirs")
        
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
        
    with open(abs_path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            f.seek(0)
            return {"raw_content": f.read()}

# =================================================================
# Dashboard 聚合接口 (Strict V13 Mode)
# =================================================================

def _extract_core_signal(json_path: Path) -> Dict[str, Any]:
    """
    辅助函数: 解析 JSON 提取 Dashboard 所需的核心字段
    [Strict Mode] 仅支持 V13+ 扁平结构 (直接在 Root 读取)
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        st = data.get("short_term") or {}
        # 直接从根目录读取，不再兼容 final_report
        return {
            "action_score": data.get("action", 0),             # e.g., 60
            "op_type": data.get("operation_type", "WAITING"),  # e.g., MARKET_ENTRY
            "op_target": data.get("operation_target", "-"),    # e.g., MARKET
            "op_volume": data.get("operation_volume", "-"),    # e.g., PILOT_SIZE
            "short_term": {
                "direction":     st.get("direction") or "-",
                "target":        st.get("target") or "-",
                "horizon_days":  st.get("horizon_days") or 0,
                "rationale":     st.get("rationale") or "",
            },
        }
    except Exception as e:
        print(f"⚠️ Error parsing {json_path.name}: {e}")
        return {
            "action_score": 0,
            "op_type": "ERROR",
            "op_target": "N/A",
            "op_volume": "N/A",
            "short_term": None,
        }

@app.get("/api/dashboard", tags=["Dashboard"])
def get_dashboard_summary():
    """
    看板接口: 返回所有标的最新状态
    """
    dashboard_data = []

    # 1. GENERAL 系列 (按 symbols.yaml `analysis_targets.generals` 列表)
    targets: List[Dict[str, str]] = [
        {"symbol": gi["symbol"], "type": "general"} for gi in list_general_symbols()
    ]

    # 2. 读取 YAML 配置追加其他标的
    if CONFIG_SYMBOLS.exists():
        try:
            with open(CONFIG_SYMBOLS, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}
                tgt_cfg = cfg.get('analysis_targets', {})
                for s in tgt_cfg.get('stocks', []):
                    targets.append({"symbol": s.upper(), "type": "stock"})
                for s in tgt_cfg.get('etfs', []):
                    targets.append({"symbol": s.upper(), "type": "etf"})
        except Exception:
            pass  # 允许部分失败，返回已有的 (至少有 GENERAL 系列)
    
    # 3. 遍历查找最新报告
    for item in targets:
        symbol = item['symbol']
        target_dir = RESULTS_DIR / symbol
        
        entry = {
            "symbol": symbol,
            "type": item['type'],
            "last_updated": None,
            "action_score": 0,
            "op_type": "WAITING",
            "op_target": "-",
            "op_volume": "-",
            "short_term": None,
            "filename": None
        }

        if target_dir.exists():
            files = list(target_dir.glob("*.json"))
            if files:
                # 寻找最新文件 (复用时间戳解析逻辑)
                file_times = []
                for f in files:
                    try:
                        parts = f.stem.split('_')
                        candidate = parts[-1]
                        dt_obj = None
                        
                        if "T" in candidate and candidate.endswith("Z"):
                            dt_obj = datetime.strptime(candidate, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                        elif candidate.isdigit():
                            dt_obj = datetime.fromtimestamp(int(candidate), tz=timezone.utc)
                        else:
                            dt_obj = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                        
                        file_times.append((dt_obj, f))
                    except:
                        continue
                
                if file_times:
                    file_times.sort(key=lambda x: x[0], reverse=True)
                    latest_dt, latest_file = file_times[0]
                    
                    # 提取信号 (Strict Mode)
                    signal = _extract_core_signal(latest_file)
                    
                    entry["last_updated"] = latest_dt.strftime('%Y-%m-%d %H:%M:%S UTC')
                    entry["action_score"] = signal["action_score"]
                    entry["op_type"] = signal["op_type"]
                    entry["op_target"] = signal["op_target"]
                    entry["op_volume"] = signal["op_volume"]
                    entry["short_term"] = signal.get("short_term")
                    entry["filename"] = latest_file.name

        dashboard_data.append(entry)

    # 4. 排序: 等待中的沉底，有动作的置顶，然后按 Symbol 排序
    dashboard_data.sort(key=lambda x: (x['op_type'] == 'WAITING', x['symbol']))
    
    return dashboard_data

# --- 启动入口 ---
if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Apex Quant API Server (V13.3 Strict New Only)")
    print(f"📁 Root: {PROJECT_ROOT}")
    print(f"📊 Results: {RESULTS_DIR}")
    print(f"🌐 URL: http://0.0.0.0:8001")
    print("=" * 60)

    uvicorn.run("apex_quant_entry:app", host="0.0.0.0", port=8001, reload=True)