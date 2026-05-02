"""
symbol_prefix.py — 用于把"无身份"的嵌套数据扁平化成带标的前缀的扁平字典。

目的：让 LLM 在阅读多标的（SPY/QQQ/DIA + 个股）数据时，每个具体指标的 key
本身就携带标的身份，避免 AI 跨标的引用数字时丢失归属信息。

设计原则：
  - 仅扁平化 dict 嵌套，list 保留为原结构（list 内字典的归属由父 key 的前缀继承）
  - 分隔符默认为下划线（不用点号——点号在 JS/jq/pandas 中会被解析为路径分隔）
  - leaf 值类型不限：scalar / list / None 都按原样保存
"""

from typing import Any, Dict


def flatten_with_symbol_prefix(symbol: str, obj: Any, sep: str = "_") -> Dict[str, Any]:
    """把嵌套 dict 扁平化，每个 leaf key 前缀为 ``{symbol}_<dotted_path>``。

    Example::

        flatten_with_symbol_prefix("QQQ", {
            "daily_technicals": {"ma_20": 639.5, "rsi_14": 75.6},
            "pivots": [{"x": 1, "y": 2}],
            "last_price": 668.36,
        })
        # ->
        # {
        #     "QQQ_daily_technicals_ma_20": 639.5,
        #     "QQQ_daily_technicals_rsi_14": 75.6,
        #     "QQQ_pivots": [{"x": 1, "y": 2}],
        #     "QQQ_last_price": 668.36,
        # }
    """
    if not isinstance(obj, dict):
        return {symbol: obj}

    result: Dict[str, Any] = {}

    def walk(prefix: str, node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                new_key = f"{prefix}{sep}{k}" if prefix else str(k)
                walk(new_key, v)
        else:
            result[prefix] = node

    walk(symbol, obj)
    return result
