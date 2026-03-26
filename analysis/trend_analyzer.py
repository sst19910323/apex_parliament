"""
analysis/trend_analyzer.py

(V9 - ISO 8601 UTC Standard)
职责: 计算 L2 (摆动点) 和 L3 (微观热机流) 的趋势结构。
修正: 
1. L3 Micro Flow Engine: 时间戳格式从 "MM-DD HH:MM" 强制修正为 ISO 8601 (YYYY-MM-DDTHH:MM:SS+00:00)。
2. 统一所有时间输出为 UTC ISO 格式，消除歧义。
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timezone

# ──────────────────────────── L2: Swing Points (战术结构) ──────────────────────────── #

def identify_swings(df: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    """
    识别高低点 (Fractals / Pivot Points)
    """
    highs = df['high']
    lows = df['low']
    
    # 简单的滚动窗口极值判断
    # 实际上这里用 argrelextrema 或 rolling max/min 都可以
    # 这里为了稳健，使用 rolling 窗口判断前后
    
    # 标记 High Pivot: 当前 High 是前后 window 范围内的最大值
    is_high = highs == highs.rolling(window=lookback*2+1, center=True).max()
    
    # 标记 Low Pivot
    is_low = lows == lows.rolling(window=lookback*2+1, center=True).min()
    
    swings = []
    
    for idx, row in df[is_high].iterrows():
        swings.append({
            'date': idx,
            'price': row['high'],
            'type': 'High'
        })
        
    for idx, row in df[is_low].iterrows():
        swings.append({
            'date': idx,
            'price': row['low'],
            'type': 'Low'
        })
    
    # 按时间排序
    swing_df = pd.DataFrame(swings)
    if not swing_df.empty:
        swing_df = swing_df.sort_values('date')
    
    return swing_df

def calculate_swing_points(df: pd.DataFrame, lookback_window: int = 20, min_swing_pct: float = 0.015, max_points: int = 20) -> Optional[Dict[str, Any]]:
    """
    计算关键摆动点 (Pivots)，并进行幅度过滤。
    """
    if df.empty or len(df) < lookback_window * 2:
        return None

    try:
        raw_swings = identify_swings(df, lookback=lookback_window)
        
        if raw_swings.empty:
            return None

        # 过滤幅度太小的波动 (Noise Filter)
        filtered_swings = []
        last_price = None
        
        for _, row in raw_swings.iterrows():
            current_price = row['price']
            if last_price is None:
                filtered_swings.append(row)
                last_price = current_price
                continue
            
            change = abs(current_price - last_price) / last_price
            if change >= min_swing_pct:
                filtered_swings.append(row)
                last_price = current_price
        
        # 限制数量，取最近的 N 个
        result_swings = filtered_swings[-max_points:]
        
        # 格式化输出
        pivots_out = []
        for row in result_swings:
            # 🔥 关键修正: 确保日期是 ISO 格式
            ts = row['date']
            if isinstance(ts, pd.Timestamp):
                ts_str = ts.isoformat()
            else:
                ts_str = str(ts)
                
            pivots_out.append({
                "date": ts_str,
                "price": round(float(row['price']), 2),
                "type": row['type']
            })
            
        return {
            "description": f"摆动点 (Lookback: {lookback_window}, MinPct: {min_swing_pct*100:.1f}%)",
            "pivots": pivots_out
        }

    except Exception as e:
        # logging.error(f"Error in calculate_swing_points: {e}")
        return None


# ──────────────────────────── L3: Micro Flow Engine (微观热机) ──────────────────────────── #

def _rdp_simplify(points, epsilon):
    """
    Ramer-Douglas-Peucker 算法简化曲线
    points: list of [x, y]
    """
    dmax = 0.0
    index = 0
    end = len(points) - 1
    
    for i in range(1, end):
        d = _perpendicular_distance(points[i], points[0], points[end])
        if d > dmax:
            index = i
            dmax = d
            
    res = []
    if dmax > epsilon:
        rec_results1 = _rdp_simplify(points[:index+1], epsilon)
        rec_results2 = _rdp_simplify(points[index:], epsilon)
        res = rec_results1[:-1] + rec_results2
    else:
        res = [points[0], points[end]]
        
    return res

def _perpendicular_distance(pt, line_start, line_end):
    if line_start[0] == line_end[0]:
        return abs(pt[0] - line_start[0])
    
    m = (line_end[1] - line_start[1]) / (line_end[0] - line_start[0])
    b = line_start[1] - m * line_start[0]
    
    # Distance from point (x0, y0) to line mx - y + b = 0
    return abs(m * pt[0] - pt[1] + b) / np.sqrt(m**2 + 1)

def calculate_simplified_trend(df: pd.DataFrame, target: int = 30) -> Optional[Dict[str, Any]]:
    """
    使用 RDP 算法提取 L3 微观热机流 (Micro Flow)。
    二分搜索 epsilon，硬上限 target 个关键点。
    盘前盘后的小噪声因幅度小在归一化空间里被自然过滤，
    真正的盘后拐点因幅度够大会自然保留。
    """
    if df.empty or len(df) < 50:
        return None

    try:
        prices = df['close'].values
        dates = df.index

        y_min, y_max = prices.min(), prices.max()
        y_range = y_max - y_min if y_max > y_min else 1.0

        points_with_idx = []
        for i in range(len(prices)):
            norm_y = (prices[i] - y_min) / y_range
            norm_x = i / len(prices)
            points_with_idx.append([norm_x, norm_y, i])

        def _rdp_idx(pts, eps):
            dmax = 0.0
            index = 0
            end = len(pts) - 1
            for i in range(1, end):
                d = _perpendicular_distance(pts[i], pts[0], pts[end])
                if d > dmax:
                    index = i
                    dmax = d
            if dmax > eps:
                r1 = _rdp_idx(pts[:index+1], eps)
                r2 = _rdp_idx(pts[index:], eps)
                return r1[:-1] + r2
            else:
                return [pts[0], pts[end]]

        # 二分搜索 epsilon，使输出点数 <= target
        lo, hi = 0.0001, 1.0
        simplified_pts = points_with_idx  # fallback
        for _ in range(30):
            mid = (lo + hi) / 2
            result = _rdp_idx(points_with_idx, mid)
            if len(result) > target:
                lo = mid  # 太多点，epsilon要更大
            else:
                simplified_pts = result
                hi = mid  # 还有余量，可以更精细
                if len(result) >= target - 5:
                    break  # 接近target了，够用
        
        # 构建输出序列
        flow_sequence = []
        prev_price = None
        
        for pt in simplified_pts:
            idx = int(pt[2])
            ts = dates[idx]
            close_p = prices[idx]
            
            # 计算该节点的相对成交量 (Relative Volume)
            # 取前后 3 根 K 线的平均量 vs 20根均量
            start_loc = max(0, idx - 3)
            end_loc = min(len(df), idx + 4)
            local_vol = df['volume'].iloc[start_loc:end_loc].mean()
            avg_vol = df['volume'].rolling(20).mean().iloc[idx]
            
            vol_rel = round(local_vol / avg_vol, 2) if avg_vol > 0 else 1.0
            
            # 计算波段涨跌幅
            pct = 0.0
            if prev_price:
                pct = round((close_p - prev_price) / prev_price * 100, 2)
            
            # 🔥 核心修正: 强制使用 ISO 8601 UTC 格式
            # 无论原始数据是 UTC 还是 Naive，都尝试标准化
            if isinstance(ts, pd.Timestamp):
                # 如果有 timezone，isoformat 会带上 +00:00
                # 如果没有 (Naive)，我们假设它是 UTC 并加上 Z (或者让它保持 Naive 但用 ISO 格式)
                # 按照 InteractiveStockFetcher V3 的逻辑，这里应该是 UTC Aware 的
                time_str = ts.isoformat()
            else:
                time_str = str(ts)

            flow_sequence.append({
                "time": time_str,  # Fixed: YYYY-MM-DDTHH:MM:SS+00:00
                "close": round(float(close_p), 2),
                "pct": pct,
                "vol_rel": vol_rel
            })
            
            prev_price = close_p
            
        return {
            "description": "DP简化流 (time=ISO8601, close=价格, pct=波段涨幅%, vol_rel=相对量比)",
            "flow_sequence": flow_sequence
        }

    except Exception as e:
        # logging.error(f"Error in calculate_simplified_trend: {e}")
        return None