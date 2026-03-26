# -----------------------------------------------------------------
# 文件路径: workflows/nodes.py
# (V9.7 - 有状态多轮对话：每 agent 维护独立 messages 线程，消除 token 浪费)
# 核心变化：
#   原始数据 / 宪法 / 格式 每 agent 只发一次（init 阶段建立线程）
#   后续轮次只追加增量：对方的上一轮/本轮发言 + 当轮任务格式
#   debate_history 仍然维护，仅用于最终 JSON 报告存储，不再用于构建 prompt
# -----------------------------------------------------------------
import json
import logging
import re
import yaml
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Callable, Optional, List

# 导入 State 定义
from .state import DebateState

# 导入 XML 解析器 (项目根目录)
import sys
_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from .xml_response_parser import parse_response as parse_debate_response
from .xml_final_report_parser import parse_final_response, parse_signoff_response

logger = logging.getLogger(__name__)


class ParliamentNodes:
    def __init__(self, prompt_manager, llm_caller: Callable, config_path: str = "config/data_sources.yaml", llm_client=None):
        self.pm = prompt_manager
        self.call_llm = llm_caller
        self.llm_client = llm_client
        self.config_path = Path(config_path)
        self.output_dir = self._resolve_output_dir()
        
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_output_dir(self) -> Path:
        """解析输出路径，优先读取配置文件"""
        path_to_load = self.config_path
        if not path_to_load.exists():
            path_to_load = Path(__file__).resolve().parents[1] / "config/data_sources.yaml"
            
        if not path_to_load.exists():
            return Path("data/debate")

        try:
            with open(path_to_load, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            relative_path = config.get("data_sources", {}).get("ai_analysis", {}).get("output_dir", "data/debate")
            project_root = path_to_load.parent.parent
            return (project_root / relative_path).resolve()
        except:
            return Path("data/debate")

    def _get_model_signatures(self) -> Dict[str, str]:
        """获取各角色使用的模型名称 (用于报告签名)"""
        role_mapping = getattr(self.llm_client, 'role_mapping', {})
        models_cfg = getattr(self.llm_client, 'models_cfg', {})

        def _get_name(role_key: str) -> str:
            model_key = role_mapping.get(role_key, 'unknown')
            cfg = models_cfg.get(model_key, {})
            return cfg.get('name', model_key)

        return {
            "zealot": _get_name("zealot"),
            "reaper": _get_name("reaper"),
            "fulcrum": _get_name("fulcrum")
        }

    # =========================================================================
    # [V9.7] 统一解析入口 + 有状态多轮辅助方法
    # =========================================================================

    def _parse_debate_output(self, raw_text: str, role: str) -> Dict[str, Any]:
        """解析辩论阶段(init/debate)的AI输出。自动兼容XML和JSON格式。"""
        return parse_debate_response(raw_text, role=role)

    def _parse_final_report(self, raw_text: str) -> Dict[str, Any]:
        """解析Fulcrum最终报告。自动兼容XML和JSON格式。"""
        return parse_final_response(raw_text)

    def _parse_signoff(self, raw_text: str, role: str) -> Dict[str, Any]:
        """解析Zealot/Reaper签收确认。自动兼容XML和JSON格式。"""
        return parse_signoff_response(raw_text, role=role)

    def _fmt_agent_turn(self, parsed: Dict[str, Any], name: str) -> str:
        """将某方的解析结果格式化为易读文本"""
        action    = parsed.get('action', '?')
        intensity = parsed.get('debate_intensity', '')
        summary   = parsed.get('summary_statement', '（无摘要）')
        analysis  = parsed.get('analysis_text', '')
        decision  = parsed.get('decision', '')

        header = f"【{name}】 action={action}"
        if intensity:
            header += f" | intensity={intensity}"
        if decision:
            header += f" | decision={decision}"

        lines = [header, f"立场摘要: {summary}"]
        if analysis:
            lines.append(f"\n分析正文:\n{analysis}")
        return "\n".join(lines)

    def _get_latest_debate_batch(self, debate_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        取最近一轮完整辩论记录（最后3条）。
        每轮由 fulcrum_debate_node / fulcrum_init_node 一次写入 Z+R+F 三条。
        """
        return debate_history[-3:] if len(debate_history) >= 3 else debate_history

    def _fmt_debate_batch(self, batch: List[Dict[str, Any]]) -> str:
        """
        格式化一批辩论记录（通常3条），注入辩论轮次的 user message。
        """
        parts = []
        for entry in batch:
            role       = entry.get('role', '?')
            round_label = entry.get('round', '?')
            content    = entry.get('content', {})
            raw_xml = entry.get('raw_xml', '')
            parts.append(f"### [{role}] {round_label}\n{raw_xml if raw_xml else json.dumps(content, ensure_ascii=False, indent=2)}")
        return "\n\n".join(parts)

    # =========================================================================
    # 1. Init Nodes — 建立各方对话线程
    #    system = 纯宪法 + 人设（后续不再重发）
    #    user   = 输出格式 + 原始数据 + 初始任务（后续不再重发）
    # =========================================================================

    def _build_init_messages(self, agent: str, state: DebateState) -> List[Dict[str, str]]:
        """构建 init 阶段的初始 messages 列表（system + user）"""
        system_content = self.pm.get_system_prompt(agent)
        output_format  = self.pm.get_output_format(agent, "init")
        task_content   = self.pm.get_task_prompt("init", state['context_type'], {
            "symbol": state.get('symbol', 'UNKNOWN'),
            **state['raw_data']
        })
        user_content = f"## 输出格式\n{output_format}\n\n{task_content}"
        return [
            {"role": "system", "content": system_content},
            {"role": "user",   "content": user_content},
        ]

    def zealot_init_node(self, state: DebateState) -> Dict[str, Any]:
        logger.info("--- [Zealot] Initializing ---")

        messages = self._build_init_messages("zealot", state)
        resp = self.call_llm(messages, role="zealot")
        messages.append({"role": "assistant", "content": resp})

        output = self._parse_debate_output(resp, "zealot")
        action = output.get('action', 50)
        return {
            "zealot_messages":     messages,
            "zealot_latest":       resp,
            "zealot_last_action":  int(action) if isinstance(action, (int, float)) else 50,
        }

    def reaper_init_node(self, state: DebateState) -> Dict[str, Any]:
        logger.info("--- [Reaper] Initializing ---")

        messages = self._build_init_messages("reaper", state)
        resp = self.call_llm(messages, role="reaper")
        messages.append({"role": "assistant", "content": resp})

        output = self._parse_debate_output(resp, "reaper")
        action = output.get('action', 50)
        return {
            "reaper_messages":     messages,
            "reaper_latest":       resp,
            "reaper_last_action":  int(action) if isinstance(action, (int, float)) else 50,
        }

    def fulcrum_init_node(self, state: DebateState) -> Dict[str, Any]:
        logger.info("--- [Fulcrum] Initializing ---")

        messages = self._build_init_messages("fulcrum", state)
        resp = self.call_llm(messages, role="fulcrum")
        messages.append({"role": "assistant", "content": resp})

        output  = self._parse_debate_output(resp, "fulcrum")
        action  = output.get('action', 50)
        decision = output.get('decision', 'CONTINUE')

        # 记录 Init 轮辩论历史（仅用于最终 JSON 报告，不再用于构建 prompt）
        zealot_content = parse_debate_response(state.get("zealot_latest", ""), role="zealot")
        reaper_content = parse_debate_response(state.get("reaper_latest", ""), role="reaper")
        batch_updates = [
            {"role": "Zealot",  "round": "Init", "content": zealot_content, "raw_xml": state.get("zealot_latest", "")},
            {"role": "Reaper",  "round": "Init", "content": reaper_content, "raw_xml": state.get("reaper_latest", "")},
            {"role": "Fulcrum", "round": "Init", "content": output,         "raw_xml": resp},
        ]

        return {
            "fulcrum_messages":     messages,
            "fulcrum_latest":       resp,
            "fulcrum_last_action":  int(action) if isinstance(action, (int, float)) else 50,
            "debate_status":        decision,
            "debate_history":       batch_updates,
            "current_phase":        "debate",
            "turn_count":           1,
        }

    # =========================================================================
    # 2. Debate Nodes — 每轮只追加增量 user message
    #
    #    Zealot / Reaper：看对方上一轮的发言（从 debate_history 取最新条目）
    #                     自己上一轮已在 assistant slot，无需重复
    #    Fulcrum：        看 Zealot + Reaper 本轮（刚生成）的发言
    #                     自己上一轮已在 assistant slot，无需重复
    # =========================================================================

    def zealot_debate_node(self, state: DebateState) -> Dict[str, Any]:
        turn = state.get('turn_count', 1)
        logger.info(f"--- [Zealot] Round {turn} ---")

        messages      = list(state['zealot_messages'])
        output_format = self.pm.get_output_format("zealot", "debate")
        symbol        = state.get('symbol', 'UNKNOWN')

        history     = state.get('debate_history', [])
        history_str = self._fmt_debate_batch(history) if history else "（无先前记录）"

        incremental_msg = (
            f"## 输出格式\n{output_format}\n\n"
            f"## 第{turn}轮辩论 | 标的：{symbol}\n\n"
            f"## 完整辩论记录\n{history_str}"
        )

        messages.append({"role": "user", "content": incremental_msg})
        resp = self.call_llm(messages, role="zealot")
        messages.append({"role": "assistant", "content": resp})

        output = self._parse_debate_output(resp, "zealot")
        action = output.get('action', 50)
        return {
            "zealot_messages":    messages,
            "zealot_latest":      resp,
            "zealot_last_action": int(action) if isinstance(action, (int, float)) else 50,
        }

    def reaper_debate_node(self, state: DebateState) -> Dict[str, Any]:
        turn = state.get('turn_count', 1)
        logger.info(f"--- [Reaper] Round {turn} ---")

        messages      = list(state['reaper_messages'])
        output_format = self.pm.get_output_format("reaper", "debate")
        symbol        = state.get('symbol', 'UNKNOWN')

        history     = state.get('debate_history', [])
        history_str = self._fmt_debate_batch(history) if history else "（无先前记录）"

        incremental_msg = (
            f"## 输出格式\n{output_format}\n\n"
            f"## 第{turn}轮辩论 | 标的：{symbol}\n\n"
            f"## 完整辩论记录\n{history_str}"
        )

        messages.append({"role": "user", "content": incremental_msg})
        resp = self.call_llm(messages, role="reaper")
        messages.append({"role": "assistant", "content": resp})

        output = self._parse_debate_output(resp, "reaper")
        action = output.get('action', 50)
        return {
            "reaper_messages":    messages,
            "reaper_latest":      resp,
            "reaper_last_action": int(action) if isinstance(action, (int, float)) else 50,
        }

    def fulcrum_debate_node(self, state: DebateState) -> Dict[str, Any]:
        turn = state.get('turn_count', 1)
        logger.info(f"--- [Fulcrum] Round {turn} ---")

        messages       = list(state['fulcrum_messages'])
        output_format  = self.pm.get_output_format("fulcrum", "debate")
        symbol         = state.get('symbol', 'UNKNOWN')

        history     = state.get('debate_history', [])
        history_str = self._fmt_debate_batch(history) if history else "（无先前记录）"

        incremental_msg = (
            f"## 输出格式\n{output_format}\n\n"
            f"## 第{turn}轮辩论 | 标的：{symbol}\n\n"
            f"## 完整辩论记录\n{history_str}"
        )

        messages.append({"role": "user", "content": incremental_msg})
        resp = self.call_llm(messages, role="fulcrum")
        messages.append({"role": "assistant", "content": resp})

        output   = self._parse_debate_output(resp, "fulcrum")
        action   = output.get('action', 50)
        decision = output.get('decision', 'CONTINUE')

        # 记录辩论历史（仅用于最终 JSON 报告存档，从 state 取本轮 Z+R 数据）
        z_this = self._parse_debate_output(state.get("zealot_latest", ""), "zealot")
        r_this = self._parse_debate_output(state.get("reaper_latest", ""), "reaper")
        batch_updates = [
            {"role": "Zealot",  "round": f"回合{turn}", "content": z_this, "raw_xml": state.get("zealot_latest", "")},
            {"role": "Reaper",  "round": f"回合{turn}", "content": r_this, "raw_xml": state.get("reaper_latest", "")},
            {"role": "Fulcrum", "round": f"回合{turn}", "content": output, "raw_xml": resp},
        ]

        return {
            "fulcrum_messages":    messages,
            "fulcrum_latest":      resp,
            "fulcrum_last_action": int(action) if isinstance(action, (int, float)) else 50,
            "debate_status":       decision,
            "debate_history":      batch_updates,
            "turn_count":          turn + 1,
        }

    # =========================================================================
    # 3. Finalize / Signoff / Save
    #
    #    Finalize：Fulcrum 的线程已有全程记录，只追加"请写报告"任务
    #    Signoff ：Zealot/Reaper 线程已有全程记录，追加最终报告内容 + 签章任务
    # =========================================================================

    def fulcrum_finalize_node(self, state: DebateState) -> Dict[str, Any]:
        logger.info("--- [Fulcrum] Finalizing ---")

        messages      = list(state['fulcrum_messages'])
        output_format = self.pm.get_output_format("fulcrum", "finalize")
        symbol        = state.get('symbol', 'UNKNOWN')
        turn          = state.get('turn_count', 1)

        history     = state.get('debate_history', [])
        history_str = self._fmt_debate_batch(history) if history else "（无记录）"

        finalize_msg = (
            f"## 完整辩论记录\n{history_str}\n\n"
            f"## 最终报告阶段 | 标的：{symbol}\n\n"
            f"请基于以上掌握的所有信息，撰写最终裁决报告。\n\n"
            f"## 输出格式\n{output_format}"
        )

        messages.append({"role": "user", "content": finalize_msg})
        resp = self.call_llm(messages, role="fulcrum")
        messages.append({"role": "assistant", "content": resp})

        output = self._parse_final_report(resp)
        report = output.get('final_report', output)
        action = report.get('action', 50)

        return {
            "fulcrum_messages":    messages,
            "final_report":        report,
            "fulcrum_last_action": int(action) if isinstance(action, (int, float)) else 50,
            "current_phase":       "signoff",
        }

    def zealot_signoff_node(self, state: DebateState) -> Dict[str, Any]:
        logger.info("--- [Zealot] Signing off ---")

        messages         = list(state['zealot_messages'])
        output_format    = self.pm.get_output_format("zealot", "signoff")
        final_report_str = json.dumps(state.get('final_report', {}), ensure_ascii=False, indent=2)
        symbol           = state.get('symbol', 'UNKNOWN')

        history     = state.get('debate_history', [])
        history_str = self._fmt_debate_batch(history) if history else "（无记录）"

        signoff_msg = (
            f"## 完整辩论记录\n{history_str}\n\n"
            f"## 签章确认 | 标的：{symbol}\n\n"
            f"## Fulcrum 最终裁决报告\n{final_report_str}\n\n"
            f"## 输出格式\n{output_format}"
        )

        messages.append({"role": "user", "content": signoff_msg})
        resp   = self.call_llm(messages, role="zealot")
        output = self._parse_signoff(resp, "zealot")

        return {
            "zealot_signoff": {
                "final_action": output.get('final_action', state.get('zealot_last_action', 50)),
                "reservation":  output.get('reservation', ''),
            }
        }

    def reaper_signoff_node(self, state: DebateState) -> Dict[str, Any]:
        logger.info("--- [Reaper] Signing off ---")

        messages         = list(state['reaper_messages'])
        output_format    = self.pm.get_output_format("reaper", "signoff")
        final_report_str = json.dumps(state.get('final_report', {}), ensure_ascii=False, indent=2)
        symbol           = state.get('symbol', 'UNKNOWN')

        history     = state.get('debate_history', [])
        history_str = self._fmt_debate_batch(history) if history else "（无记录）"

        signoff_msg = (
            f"## 完整辩论记录\n{history_str}\n\n"
            f"## 签章确认 | 标的：{symbol}\n\n"
            f"## Fulcrum 最终裁决报告\n{final_report_str}\n\n"
            f"## 输出格式\n{output_format}"
        )

        messages.append({"role": "user", "content": signoff_msg})
        resp   = self.call_llm(messages, role="reaper")
        output = self._parse_signoff(resp, "reaper")

        return {
            "reaper_signoff": {
                "final_action": output.get('final_action', state.get('reaper_last_action', 50)),
                "reservation":  output.get('reservation', ''),
            }
        }

    # =========================================================================
    # 5. Data Saver Node (不变)
    # =========================================================================
    def data_saver_node(self, state: DebateState) -> Dict[str, Any]:
        logger.info("--- [System] Saving Data ---")
        final_json = state.get('final_report', {})
        if not final_json:
            logger.error("No final report to save!")
            return {}

        z_sig = state.get('zealot_signoff', {})
        r_sig = state.get('reaper_signoff', {})
        
        # --- dissent ---
        final_json['dissent'] = {
            "zealot_final_action": z_sig.get('final_action', 50),
            "zealot_reservation": z_sig.get('reservation', ''),
            "reaper_final_action": r_sig.get('final_action', 50),
            "reaper_reservation": r_sig.get('reservation', '')
        }
        
        # --- signatures: 直接用模型 name ---
        final_json['signatures'] = self._get_model_signatures()
        
        # --- debate_history（去掉 raw_xml，只保存解析后的 content）---
        final_json['debate_history'] = [
            {k: v for k, v in entry.items() if k != 'raw_xml'}
            for entry in state.get('debate_history', [])
        ]

        # --- data_files: [修复] 用正确的 key 'data_files' ---
        data_files = state.get('data_files', {})
        if data_files:
            final_json['data_files'] = data_files

        try:
            symbol = state.get('symbol', 'GENERAL').upper()
            data_ts_iso = state.get('data_timestamp_for_report')
            
            if data_ts_iso:
                file_ts_str = data_ts_iso.replace("-", "").replace(":", "")
            else:
                now_utc = datetime.now(timezone.utc)
                file_ts_str = now_utc.strftime("%Y%m%dT%H%M%SZ")

            filename = f"{symbol}_Analysis_{file_ts_str}.json"
            
            if self.output_dir:
                symbol_dir = self.output_dir / symbol
                symbol_dir.mkdir(parents=True, exist_ok=True)
                save_path = symbol_dir / filename
                
                final_json['market_data_timestamp_utc'] = data_ts_iso
                final_json['report_generated_at'] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(final_json, f, indent=2, ensure_ascii=False)
                logger.info(f"✅ Final report saved to: {save_path}")
            else:
                logger.warning("⚠️ Output directory not resolved, report NOT saved.")
                
        except Exception as e:
            logger.error(f"❌ Save failed: {e}")

        return {"final_report": final_json}