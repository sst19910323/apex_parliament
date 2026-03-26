"""
xml_response_parser.py - AI辩论输出XML解析器

将AI输出的XML格式机械转换为系统内部使用的JSON dict。
三层容错:
  1. 标准XML解析 (xml.etree.ElementTree)
  2. 正则提取 fallback (处理AI输出的不规范XML)
  3. 默认值兜底 (确保下游永远拿到完整结构)
"""

import re
import json
import logging
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


# ── 默认值 ──

DEFAULT_RESPONSE = {
    "debate_intensity": "MEDIUM",
    "action": 50,
    "operation_type": "HOLD_NEUTRAL",
    "operation_target": "N/A",
    "operation_volume": "N/A",
    "preliminary_mentality": [
        {"name": "wait_and_see", "probability": 1.0}
    ],
    "summary_statement": "[解析失败]",
    "analysis_text": "[解析失败]",
}


# ── 主入口 ──

def parse_debate_xml(raw_text: str, role: str = "unknown") -> Dict[str, Any]:
    """
    解析AI输出的XML，返回与原JSON格式兼容的dict。
    
    Args:
        raw_text: AI的原始输出文本
        role: 角色名 (zealot/reaper/fulcrum)，用于日志
    
    Returns:
        与原JSON格式完全兼容的dict
    """
    if not raw_text or not raw_text.strip():
        logger.warning(f"[XMLParser][{role}] Empty response, using defaults.")
        return dict(DEFAULT_RESPONSE)
    
    # 预处理: 提取<response>...</response>块
    cleaned = _extract_response_block(raw_text)
    
    # 第一层: 标准XML解析
    result = _parse_xml_strict(cleaned, role)
    
    # 第二层: 正则fallback
    if result is None:
        logger.warning(f"[XMLParser][{role}] Strict XML parse failed, trying regex fallback.")
        result = _parse_regex_fallback(raw_text, role)
    
    # 第三层: 默认值兜底
    if result is None:
        logger.error(f"[XMLParser][{role}] All parsing failed. Using defaults.")
        result = dict(DEFAULT_RESPONSE)
        result["analysis_text"] = f"[原始输出解析失败]\n\n{raw_text[:2000]}"
    
    # 类型修正 & 校验
    result = _validate_and_fix(result, role)
    
    return result


# ── 预处理 ──

def _extract_response_block(text: str) -> str:
    """从AI输出中提取<response>...</response>块，去掉前后废话"""
    # 去掉markdown代码块包裹
    text = re.sub(r'```xml\s*', '', text)
    text = re.sub(r'```\s*$', '', text)
    text = text.strip()
    
    # 提取 <response>...</response>
    match = re.search(r'<response\b[^>]*>(.*?)</response>', text, re.DOTALL)
    if match:
        return f"<response>{match.group(1)}</response>"
    
    # 如果没有response标签但有其他XML标签，包一层
    if '<' in text and '>' in text:
        return f"<response>{text}</response>"
    
    return text


# ── 第一层: 标准XML解析 ──

def _parse_xml_strict(xml_str: str, role: str) -> Optional[Dict[str, Any]]:
    """用标准XML parser解析"""
    try:
        root = ET.fromstring(xml_str)
        result = {}
        
        # 简单文本字段
        simple_fields = [
            "debate_intensity", "action", "operation_type",
            "operation_target", "operation_volume",
            "summary_statement", "analysis_text", "decision"
        ]
        
        for field in simple_fields:
            elem = root.find(field)
            if elem is not None and elem.text:
                result[field] = elem.text.strip()
        
        # mentality数组: 优先从<mentality>子标签找，fallback到root下散落的<item>
        mentality_elem = root.find("mentality")
        search_root = mentality_elem if mentality_elem is not None else root
        items = []
        for item in search_root.findall("item"):
            name = item.get("name", "")
            prob = item.get("probability", "0.5")
            if name:
                items.append({
                    "name": name.strip(),
                    "probability": _safe_float(prob, 0.5)
                })
        if items:
            result["preliminary_mentality"] = items
        
        if not result:
            return None
            
        logger.info(f"[XMLParser][{role}] Strict XML parse OK.")
        return result
        
    except ET.ParseError as e:
        logger.debug(f"[XMLParser][{role}] XML ParseError: {e}")
        return None
    except Exception as e:
        logger.debug(f"[XMLParser][{role}] XML unexpected error: {e}")
        return None


# ── 第二层: 正则Fallback ──

def _parse_regex_fallback(text: str, role: str) -> Optional[Dict[str, Any]]:
    """用正则从文本中提取各字段，即使XML不合法也能提取"""
    result = {}
    extracted_count = 0
    
    # 简单标签: <field>value</field>
    simple_patterns = {
        "debate_intensity": r'<debate_intensity>\s*(.*?)\s*</debate_intensity>',
        "action": r'<action>\s*(.*?)\s*</action>',
        "operation_type": r'<operation_type>\s*(.*?)\s*</operation_type>',
        "operation_target": r'<operation_target>\s*(.*?)\s*</operation_target>',
        "operation_volume": r'<operation_volume>\s*(.*?)\s*</operation_volume>',
        "decision": r'<decision>\s*(.*?)\s*</decision>',
    }
    
    for field, pattern in simple_patterns.items():
        match = re.search(pattern, text, re.DOTALL)
        if match:
            result[field] = match.group(1).strip()
            extracted_count += 1
    
    # CDATA字段: <field><![CDATA[...]]></field> 或 <field>...</field>
    for field in ["summary_statement", "analysis_text"]:
        # 先尝试CDATA
        cdata_pattern = rf'<{field}>\s*<!\[CDATA\[(.*?)\]\]>\s*</{field}>'
        match = re.search(cdata_pattern, text, re.DOTALL)
        if match:
            result[field] = match.group(1).strip()
            extracted_count += 1
        else:
            # 普通标签
            plain_pattern = rf'<{field}>\s*(.*?)\s*</{field}>'
            match = re.search(plain_pattern, text, re.DOTALL)
            if match:
                result[field] = match.group(1).strip()
                extracted_count += 1
    
    # mentality items: <item name="xxx" probability="0.7"/> (支持属性顺序颠倒)
    mentality_items = re.findall(
        r'<item\s+(?:name=["\']([^"\']+)["\']\s+probability=["\']([^"\']+)["\']|probability=["\']([^"\']+)["\']\s+name=["\']([^"\']+)["\'])',
        text
    )
    # 统一格式: findall返回4组，取非空的那对
    mentality_items = [
        (g[0] or g[3], g[1] or g[2]) for g in mentality_items
    ]
    if mentality_items:
        result["preliminary_mentality"] = [
            {"name": name.strip(), "probability": _safe_float(prob, 0.5)}
            for name, prob in mentality_items
        ]
        extracted_count += 1
    
    if extracted_count >= 2:
        logger.info(f"[XMLParser][{role}] Regex fallback extracted {extracted_count} fields.")
        return result
    
    logger.warning(f"[XMLParser][{role}] Regex fallback only got {extracted_count} fields, insufficient.")
    return None


# ── 校验 & 修正 ──

VALID_INTENSITIES = {"LOW", "MEDIUM", "HIGH"}
VALID_OP_TYPES = {"MARKET_ENTRY", "LIMIT_ENTRY", "HOLD_NEUTRAL", "TRIM_POSITION", "LIQUIDATE_NOW"}
VALID_VOLUMES = {"PILOT_SIZE", "STANDARD_SIZE", "AGGRESSIVE_SIZE", "N/A"}
VALID_MENTALITIES = {
    "buy_the_dip", "fomo_buy", "profit_taking", "cut_losses_aggressively",
    "cut_losses_reluctantly", "hold_and_ride_profit", "trapped_hold",
    "wait_for_confirmation", "wait_and_see", "avoid_uncertainty",
    "bottom_fishing", "short_squeeze_chase", "sell_on_strength",
    "hedge_position", "average_down", "average_up", "all_in",
    "rotate_sector", "deleveraging", "contrarian_bet"
}


def _validate_and_fix(data: Dict[str, Any], role: str) -> Dict[str, Any]:
    """确保所有字段存在且类型正确"""
    
    # action -> int, 范围 0-100
    action_raw = data.get("action", 50)
    data["action"] = max(0, min(100, _safe_int(action_raw, 50)))
    
    # debate_intensity 枚举校验
    intensity = str(data.get("debate_intensity", "MEDIUM")).upper().strip()
    data["debate_intensity"] = intensity if intensity in VALID_INTENSITIES else "MEDIUM"
    
    # operation_type 枚举校验
    op_type = str(data.get("operation_type", "HOLD_NEUTRAL")).upper().strip()
    data["operation_type"] = op_type if op_type in VALID_OP_TYPES else "HOLD_NEUTRAL"
    
    # operation_volume 枚举校验
    volume = str(data.get("operation_volume", "N/A")).upper().strip()
    data["operation_volume"] = volume if volume in VALID_VOLUMES else "N/A"
    
    # operation_target
    if "operation_target" not in data:
        data["operation_target"] = "N/A"
    
    # summary_statement
    if "summary_statement" not in data or not data["summary_statement"]:
        data["summary_statement"] = "[未提供]"
    
    # analysis_text
    if "analysis_text" not in data or not data["analysis_text"]:
        data["analysis_text"] = "[未提供]"
    
    # preliminary_mentality
    if "preliminary_mentality" not in data or not data["preliminary_mentality"]:
        data["preliminary_mentality"] = [{"name": "wait_and_see", "probability": 1.0}]
    else:
        # 过滤无效心态
        valid_items = []
        for item in data["preliminary_mentality"]:
            if isinstance(item, dict) and item.get("name") in VALID_MENTALITIES:
                item["probability"] = _safe_float(item.get("probability", 0.5), 0.5)
                valid_items.append(item)
        data["preliminary_mentality"] = valid_items if valid_items else [
            {"name": "wait_and_see", "probability": 1.0}
        ]
    
    # decision (仅Fulcrum)
    if "decision" in data:
        decision = str(data["decision"]).upper().strip()
        data["decision"] = decision if decision in {"CONTINUE", "TERMINATE"} else "CONTINUE"
    
    return data


# ── 工具函数 ──

def _safe_int(val, default: int = 50) -> int:
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return default

def _safe_float(val, default: float = 0.5) -> float:
    try:
        return float(str(val).strip())
    except (ValueError, TypeError):
        return default


# ── 便捷方法: 兼容旧的JSON解析调用 ──

def parse_response(raw_text: str, role: str = "unknown") -> Dict[str, Any]:
    """
    统一入口: 自动检测输入是JSON还是XML，返回统一的dict。
    用于替换原有的JSON解析逻辑，实现平滑迁移。
    """
    text = raw_text.strip()
    
    # 如果看起来像JSON (以{开头)，先尝试JSON解析
    if text.startswith('{'):
        try:
            # 提取JSON块
            brace_count = 0
            json_end = -1
            for i, ch in enumerate(text):
                if ch == '{': brace_count += 1
                elif ch == '}': brace_count -= 1
                if brace_count == 0:
                    json_end = i + 1
                    break
            
            if json_end > 0:
                result = json.loads(text[:json_end])
                if isinstance(result, dict):
                    logger.info(f"[Parser][{role}] Parsed as JSON (legacy format).")
                    return _validate_and_fix(result, role)
        except json.JSONDecodeError:
            logger.debug(f"[Parser][{role}] JSON parse failed, trying XML.")
    
    # 否则按XML解析
    return parse_debate_xml(raw_text, role)


if __name__ == "__main__":
    # 测试用例
    test_xml = """
    <response>
        <debate_intensity>HIGH</debate_intensity>
        <action>72</action>
        <operation_type>MARKET_ENTRY</operation_type>
        <operation_target>MARKET</operation_target>
        <operation_volume>STANDARD_SIZE</operation_volume>
        <mentality>
            <item name="buy_the_dip" probability="0.6"/>
            <item name="hold_and_ride_profit" probability="0.4"/>
        </mentality>
        <summary_statement><![CDATA[技术面超卖反弹信号明确，基本面无重大利空，建议逢低建仓。]]></summary_statement>
        <analysis_text><![CDATA[
从技术面来看，RSI已经跌入30以下的超卖区间，MACD出现金叉迹象。
布林带下轨提供了强支撑，成交量在低位有放大趋势。

基本面方面，最新财报数据显示营收同比增长15%，超出市场预期。
"管理层在电话会议中提到"下半年增长加速"的预期。

综合来看，短期回调提供了良好的入场时机。
        ]]></analysis_text>
    </response>
    """
    
    result = parse_debate_xml(test_xml, "zealot")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    # 测试正则fallback (故意写坏的XML)
    test_broken = """
    好的，以下是我的分析：
    <debate_intensity>HIGH</debate_intensity>
    <action>80</action>
    <operation_type>MARKET_ENTRY</operation_type>
    <operation_target>MARKET</operation_target>
    <operation_volume>AGGRESSIVE_SIZE</operation_volume>
    <item name="fomo_buy" probability="0.8"/>
    <item name="buy_the_dip" probability="0.2"/>
    <summary_statement><![CDATA[强势突破，追！]]></summary_statement>
    <analysis_text><![CDATA[这是一段包含"引号"和各种<特殊>字符的文本，JSON肯定爆炸。]]></analysis_text>
    """
    
    result2 = parse_debate_xml(test_broken, "zealot_broken")
    print("\n--- Regex Fallback Result ---")
    print(json.dumps(result2, ensure_ascii=False, indent=2))
