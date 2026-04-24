"""
xml_final_report_parser.py - 最终报告XML解析器

将Chronicler(史官)输出的final_report XML机械转换为系统内部JSON dict。
三层容错: 标准XML → 正则fallback → 默认值兜底
"""

import re
import json
import logging
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


# ── 默认值 ──

DEFAULT_FINAL_REPORT = {
    "final_report": {
        "debate_summary": "[解析失败]",
        "mentality": [{"name": "wait_and_see", "probability": 1.0}],
        "reasoning": {"key_drivers": [], "risks": []},
        "risk_management": {
            "stop_loss": "N/A",
            "take_profit": "N/A",
            "max_drawdown_tolerance": "N/A",
            "review_triggers": []
        },
        "action": 50,
        "operation_type": "HOLD_NEUTRAL",
        "operation_target": "N/A",
        "operation_volume": "N/A",
        "dissent": {
            "zealot_final_action": 50, "zealot_reservation": "N/A",
            "reaper_final_action": 50, "reaper_reservation": "N/A",
            "fulcrum_final_action": 50, "fulcrum_reservation": "N/A"
        },
        "statement": "[解析失败]"
    }
}

DEFAULT_SIGNOFF = {
    "final_action": 50,
    "reservation": ""
}


# ── 工具函数 ──

def _safe_int(val, default: int = 50) -> int:
    try: return int(float(str(val).strip()))
    except: return default

def _safe_float(val, default: float = 0.5) -> float:
    try: return float(str(val).strip())
    except: return default

def _get_text(elem, tag: str, default: str = "") -> str:
    """从XML元素中安全提取子标签文本"""
    child = elem.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return default

def _get_all_texts(elem, tag: str) -> List[str]:
    """提取同名子标签的所有文本"""
    return [e.text.strip() for e in elem.findall(tag) if e.text]

def _extract_block(text: str, tag: str) -> str:
    """从原始文本中提取<tag>...</tag>块"""
    # 去掉markdown代码块
    text = re.sub(r'```xml\s*', '', text)
    text = re.sub(r'```\s*$', '', text)
    
    match = re.search(rf'<{tag}\b[^>]*>(.*?)</{tag}>', text, re.DOTALL)
    if match:
        return f"<{tag}>{match.group(1)}</{tag}>"
    return text.strip()

def _regex_cdata_or_plain(text: str, tag: str) -> str:
    """正则提取标签内容，支持CDATA"""
    # CDATA
    m = re.search(rf'<{tag}>\s*<!\[CDATA\[(.*?)\]\]>\s*</{tag}>', text, re.DOTALL)
    if m: return m.group(1).strip()
    # 普通
    m = re.search(rf'<{tag}>\s*(.*?)\s*</{tag}>', text, re.DOTALL)
    if m: return m.group(1).strip()
    return ""


# ══════════════════════════════════════════════════════════════
# Final Report 解析
# ══════════════════════════════════════════════════════════════

def parse_final_report_xml(raw_text: str) -> Dict[str, Any]:
    """
    解析Chronicler(史官)最终报告XML，返回与原JSON格式兼容的dict。
    """
    if not raw_text or not raw_text.strip():
        logger.warning("[FinalReportParser] Empty input.")
        return _deep_copy_default()
    
    cleaned = _extract_block(raw_text, "final_report")
    
    # 第一层: 标准XML
    result = _parse_final_strict(cleaned)
    
    # 第二层: 正则fallback
    if result is None:
        logger.warning("[FinalReportParser] Strict parse failed, trying regex.")
        result = _parse_final_regex(raw_text)
    
    # 第三层: 默认值
    if result is None:
        logger.error("[FinalReportParser] All parsing failed.")
        result = _deep_copy_default()
        result["final_report"]["debate_summary"] = f"[解析失败]\n\n{raw_text[:3000]}"
    
    # 校验
    _validate_final_report(result)
    return result


def _deep_copy_default() -> Dict:
    import copy
    return copy.deepcopy(DEFAULT_FINAL_REPORT)


def _parse_final_strict(xml_str: str) -> Optional[Dict]:
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return None
    
    r = {}
    
    # Simple text fields (zh-only core)
    for field in ["debate_summary", "statement",
                   "action", "operation_type", "operation_target", "operation_volume"]:
        r[field] = _get_text(root, field, "")
    
    # mentality
    ment_elem = root.find("mentality")
    search = ment_elem if ment_elem is not None else root
    items = []
    for item in search.findall("item"):
        name = item.get("name", "")
        prob = item.get("probability", "0.5")
        if name:
            items.append({"name": name.strip(), "probability": _safe_float(prob)})
    r["mentality"] = items if items else [{"name": "wait_and_see", "probability": 1.0}]
    
    # reasoning.key_drivers
    drivers = []
    kd_elem = root.find(".//key_drivers")
    if kd_elem is not None:
        for drv in kd_elem.findall("driver"):
            driver = {
                "direction": drv.get("direction", ""),
                "category": drv.get("category", ""),
                "weight": drv.get("weight", "medium"),
                "factor": _get_text(drv, "factor"),
                "evidence": _get_all_texts(drv, "evidence"),
            }
            drivers.append(driver)

    # reasoning.risks
    risks = []
    risks_elem = root.find(".//risks")
    if risks_elem is not None:
        for rsk in risks_elem.findall("risk"):
            risk = {
                "risk": _get_text(rsk, "description"),
                "probability": rsk.get("probability", "medium"),
                "impact": rsk.get("impact", "medium"),
                "mitigation": _get_text(rsk, "mitigation"),
                "trigger": _get_text(rsk, "trigger"),
            }
            risks.append(risk)
    
    r["reasoning"] = {"key_drivers": drivers, "risks": risks}
    
    # risk_management (zh-only)
    rm_elem = root.find("risk_management")
    rm = {}
    if rm_elem is not None:
        for field in ["stop_loss", "take_profit", "max_drawdown_tolerance"]:
            rm[field] = _get_text(rm_elem, field, "N/A")

        rt_elem = rm_elem.find("review_triggers")
        rm["review_triggers"] = _get_all_texts(rt_elem, "trigger") if rt_elem is not None else []
    r["risk_management"] = rm if rm else DEFAULT_FINAL_REPORT["final_report"]["risk_management"]
    
    # dissent (three-way: Zealot / Reaper / Fulcrum)
    dis_elem = root.find("dissent")
    dissent = {}
    if dis_elem is not None:
        dissent["zealot_final_action"] = _get_text(dis_elem, "zealot_final_action", "50")
        dissent["zealot_reservation"] = _get_text(dis_elem, "zealot_reservation", "N/A")
        dissent["reaper_final_action"] = _get_text(dis_elem, "reaper_final_action", "50")
        dissent["reaper_reservation"] = _get_text(dis_elem, "reaper_reservation", "N/A")
        dissent["fulcrum_final_action"] = _get_text(dis_elem, "fulcrum_final_action", "50")
        dissent["fulcrum_reservation"] = _get_text(dis_elem, "fulcrum_reservation", "N/A")
    r["dissent"] = dissent if dissent else DEFAULT_FINAL_REPORT["final_report"]["dissent"]
    
    if not r.get("debate_summary") and not r.get("action"):
        return None
    
    logger.info("[FinalReportParser] Strict XML parse OK.")
    return {"final_report": r}


def _parse_final_regex(text: str) -> Optional[Dict]:
    """Regex fallback for final_report extraction (zh-only core).
    All expected text-field keys are always written (empty string fallback) so
    downstream schema stays consistent regardless of which parser path ran.
    """
    r = {}
    count = 0

    # Text fields: always write the key, even when extraction yields empty.
    for field in ["debate_summary", "statement"]:
        val = _regex_cdata_or_plain(text, field)
        r[field] = val  # may be ""
        if val:
            count += 1

    # Simple fields
    for field in ["action", "operation_type", "operation_target", "operation_volume"]:
        m = re.search(rf'<{field}>\s*(.*?)\s*</{field}>', text, re.DOTALL)
        if m:
            r[field] = m.group(1).strip()
            count += 1

    # mentality
    mentality_items = re.findall(
        r'<item\s+(?:name=["\']([^"\']+)["\']\s+probability=["\']([^"\']+)["\']|probability=["\']([^"\']+)["\']\s+name=["\']([^"\']+)["\'])',
        text
    )
    items = [
        {"name": (g[0] or g[3]).strip(), "probability": _safe_float(g[1] or g[2])}
        for g in mentality_items if (g[0] or g[3])
    ]
    r["mentality"] = items if items else [{"name": "wait_and_see", "probability": 1.0}]

    # dissent (three-way)
    dissent = {}
    for field in [
        "zealot_final_action", "zealot_reservation",
        "reaper_final_action", "reaper_reservation",
        "fulcrum_final_action", "fulcrum_reservation",
    ]:
        val = _regex_cdata_or_plain(text, field)
        if val: dissent[field] = val
    r["dissent"] = dissent if dissent else DEFAULT_FINAL_REPORT["final_report"]["dissent"]

    # risk_management (zh-only scalar fields)
    rm = {}
    for field in ["stop_loss", "take_profit", "max_drawdown_tolerance"]:
        val = _regex_cdata_or_plain(text, field)
        if val: rm[field] = val
    r["risk_management"] = rm if rm else DEFAULT_FINAL_REPORT["final_report"]["risk_management"]
    
    # reasoning - 简化提取drivers和risks
    r["reasoning"] = {"key_drivers": [], "risks": []}
    
    if count >= 2:
        logger.info(f"[FinalReportParser] Regex fallback extracted {count} fields.")
        return {"final_report": r}
    
    return None


def _validate_final_report(data: Dict):
    """Validate and normalize final_report dict (zh-only core).
    Guarantees:
      1. Every key in DEFAULT_FINAL_REPORT["final_report"] exists in fr (missing
         -> filled from default). Prevents "sometimes-missing field" drift
         between strict/regex parse paths.
      2. action / operation_type / operation_volume sanitized to enum-safe values.
    """
    fr = data.get("final_report", {})

    # (1) Schema completion: fill any missing top-level key from default
    import copy
    for k, default_v in DEFAULT_FINAL_REPORT["final_report"].items():
        if k not in fr:
            fr[k] = copy.deepcopy(default_v)

    # (2) action / operation_type / operation_volume sanitation
    fr["action"] = max(0, min(100, _safe_int(fr.get("action", 50))))

    op_type = str(fr.get("operation_type", "HOLD_NEUTRAL")).upper().strip()
    valid_ops = {"MARKET_ENTRY", "LIMIT_ENTRY", "HOLD_NEUTRAL", "TRIM_POSITION", "LIQUIDATE_NOW"}
    fr["operation_type"] = op_type if op_type in valid_ops else "HOLD_NEUTRAL"

    volume = str(fr.get("operation_volume", "N/A")).upper().strip()
    valid_vols = {"PILOT_SIZE", "STANDARD_SIZE", "AGGRESSIVE_SIZE", "N/A"}
    fr["operation_volume"] = volume if volume in valid_vols else "N/A"

    if "operation_target" not in fr:
        fr["operation_target"] = "N/A"

    # dissent: coerce action fields to int (three-way)
    dissent = fr.get("dissent", {}) or {}
    dissent["zealot_final_action"] = _safe_int(dissent.get("zealot_final_action", 50))
    dissent["reaper_final_action"] = _safe_int(dissent.get("reaper_final_action", 50))
    dissent["fulcrum_final_action"] = _safe_int(dissent.get("fulcrum_final_action", 50))
    fr["dissent"] = dissent

    data["final_report"] = fr


# ══════════════════════════════════════════════════════════════
# Signoff 解析
# ══════════════════════════════════════════════════════════════

def parse_signoff_xml(raw_text: str, role: str = "unknown") -> Dict[str, Any]:
    """解析Zealot/Reaper的签收确认"""
    if not raw_text or not raw_text.strip():
        return dict(DEFAULT_SIGNOFF)
    
    cleaned = _extract_block(raw_text, "signoff")
    
    # 标准XML
    try:
        root = ET.fromstring(cleaned)
        result = {
            "final_action": _safe_int(_get_text(root, "final_action", "50")),
            "reservation": _get_text(root, "reservation", "")
        }
        logger.info(f"[SignoffParser][{role}] XML parse OK.")
        return result
    except ET.ParseError:
        pass
    
    # 正则fallback
    action_m = re.search(r'<final_action>\s*(\d+)\s*</final_action>', raw_text)
    resv = _regex_cdata_or_plain(raw_text, "reservation")
    
    if action_m:
        logger.info(f"[SignoffParser][{role}] Regex fallback OK.")
        return {
            "final_action": _safe_int(action_m.group(1)),
            "reservation": resv
        }
    
    logger.warning(f"[SignoffParser][{role}] All parsing failed.")
    return dict(DEFAULT_SIGNOFF)


# ══════════════════════════════════════════════════════════════
# 统一入口 (兼容旧JSON)
# ══════════════════════════════════════════════════════════════

def parse_final_response(raw_text: str) -> Dict[str, Any]:
    """
    自动检测JSON/XML，返回统一dict。平滑迁移用。
    """
    text = raw_text.strip()
    
    if text.startswith('{'):
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                if "final_report" in result:
                    logger.info("[FinalParser] Parsed as JSON (legacy).")
                    _validate_final_report(result)
                    return result
        except json.JSONDecodeError:
            pass
    
    return parse_final_report_xml(raw_text)


def parse_signoff_response(raw_text: str, role: str = "unknown") -> Dict[str, Any]:
    """自动检测JSON/XML signoff"""
    text = raw_text.strip()
    
    if text.startswith('{'):
        try:
            result = json.loads(text)
            if isinstance(result, dict) and "final_action" in result:
                logger.info(f"[SignoffParser][{role}] Parsed as JSON (legacy).")
                result["final_action"] = _safe_int(result.get("final_action", 50))
                return result
        except json.JSONDecodeError:
            pass
    
    return parse_signoff_xml(raw_text, role)


# ══════════════════════════════════════════════════════════════
# 测试
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    test_xml = """
    <final_report>
        <debate_summary><![CDATA[Zealot从75开始看多，主张技术面超卖反弹。Reaper从30看空，认为基本面恶化。经过3轮辩论，三方在55附近达成共识。]]></debate_summary>
        <mentality>
            <item name="wait_for_confirmation" probability="0.5"/>
            <item name="buy_the_dip" probability="0.35"/>
        </mentality>
        <reasoning>
            <key_drivers>
                <driver direction="bullish" category="technical" weight="high">
                    <factor><![CDATA[RSI超卖反弹]]></factor>
                    <evidence><![CDATA[RSI(14)=28，触及30以下超卖区]]></evidence>
                    <evidence><![CDATA[MACD柱状图收窄]]></evidence>
                </driver>
                <driver direction="bearish" category="fundamental" weight="medium">
                    <factor><![CDATA[营收增速放缓]]></factor>
                    <evidence><![CDATA[Q3营收同比+8%，Q2为+15%]]></evidence>
                </driver>
            </key_drivers>
            <risks>
                <risk probability="medium" impact="high">
                    <description><![CDATA[宏观加息预期升温]]></description>
                    <mitigation><![CDATA[设置止损位跌破$145清仓]]></mitigation>
                    <trigger><![CDATA[10Y国债收益率突破4.8%]]></trigger>
                </risk>
            </risks>
        </reasoning>
        <risk_management>
            <stop_loss><![CDATA[跌破$145清仓]]></stop_loss>
            <take_profit><![CDATA[$165分批止盈]]></take_profit>
            <max_drawdown_tolerance>8%</max_drawdown_tolerance>
            <review_triggers>
                <trigger><![CDATA[财报发布后重新评估]]></trigger>
                <trigger><![CDATA[VIX突破25]]></trigger>
            </review_triggers>
        </risk_management>
        <action>57</action>
        <operation_type>LIMIT_ENTRY</operation_type>
        <operation_target>$148.50</operation_target>
        <operation_volume>PILOT_SIZE</operation_volume>
        <dissent>
            <zealot_final_action>65</zealot_final_action>
            <zealot_reservation><![CDATA[仍认为技术面信号更强，action应在60以上]]></zealot_reservation>
            <reaper_final_action>48</reaper_final_action>
            <reaper_reservation><![CDATA[基本面隐患未消，建议更谨慎]]></reaper_reservation>
            <fulcrum_final_action>55</fulcrum_final_action>
            <fulcrum_reservation><![CDATA[无]]></fulcrum_reservation>
        </dissent>
        <statement><![CDATA[技术超卖提供入场窗口，但基本面放缓需限仓试探，$145为硬止损。]]></statement>
    </final_report>
    """
    
    result = parse_final_report_xml(test_xml)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    print("\n--- Signoff Test ---")
    signoff_xml = """
    <signoff>
        <final_action>62</final_action>
        <reservation><![CDATA[基本同意，但止损位建议收紧到$146]]></reservation>
    </signoff>
    """
    print(json.dumps(parse_signoff_xml(signoff_xml, "zealot"), ensure_ascii=False, indent=2))
