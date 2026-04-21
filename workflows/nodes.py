# -----------------------------------------------------------------
# 文件路径: workflows/nodes.py
# (V10.0 - 四方架构：Z/R/F 三辩论者 + Chronicler 史官)
#
# 变化要点：
#   - Fulcrum从"仲裁者"剥离为纯辩论者，与Z/R同层
#   - 新增Chronicler：秩序维护(CONTINUE/TERMINATE) + 写最终报告 + 记忆管理
#   - Chronicler不接触raw_data，仅基于辩论记录工作
#   - 三方签章统一（Fulcrum也签章）
#   - debate_history和turn_count由chronicler_moderation_node维护
# -----------------------------------------------------------------
import json
import logging
import re
import yaml
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Callable, Optional, List

from .state import DebateState

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
            "zealot":     _get_name("zealot"),
            "reaper":     _get_name("reaper"),
            "fulcrum":    _get_name("fulcrum"),
            "chronicler": _get_name("chronicler"),
        }

    # =========================================================================
    # 解析辅助
    # =========================================================================

    def _parse_debate_output(self, raw_text: str, role: str) -> Dict[str, Any]:
        return parse_debate_response(raw_text, role=role)

    def _parse_final_report(self, raw_text: str) -> Dict[str, Any]:
        return parse_final_response(raw_text)

    def _parse_signoff(self, raw_text: str, role: str) -> Dict[str, Any]:
        return parse_signoff_response(raw_text, role=role)

    def _parse_moderation(self, raw_text: str) -> Dict[str, Any]:
        """解析chronicler的CONTINUE/TERMINATE决策 + 三方精简版本"""
        decision = "CONTINUE"
        reason = ""
        polished = {"zealot": "", "reaper": "", "fulcrum": ""}

        dm = re.search(r"<decision>\s*(\w+)\s*</decision>", raw_text, re.IGNORECASE)
        if dm:
            decision = dm.group(1).upper()

        rm = re.search(r"<reason>(?:\s*<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</reason>", raw_text, re.DOTALL)
        if rm:
            reason = rm.group(1).strip()

        # 解析 round_memory 下的三个子节点
        rm_block = re.search(r"<round_memory>(.*?)</round_memory>", raw_text, re.DOTALL)
        if rm_block:
            block = rm_block.group(1)
            for role in ("zealot", "reaper", "fulcrum"):
                m = re.search(
                    rf"<{role}>(?:\s*<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</{role}>",
                    block, re.DOTALL
                )
                if m:
                    polished[role] = m.group(1).strip()

        if decision not in ("CONTINUE", "TERMINATE"):
            decision = "CONTINUE"
        return {"decision": decision, "reason": reason, "polished": polished}

    def _fmt_debate_batch(self, batch: List[Dict[str, Any]]) -> str:
        """格式化辩论记录；优先使用Chronicler精简版(polished_text)，兜底回raw_xml/content"""
        parts = []
        for entry in batch:
            role        = entry.get('role', '?')
            round_label = entry.get('round', '?')
            polished    = entry.get('polished_text', '')
            raw_xml     = entry.get('raw_xml', '')
            content     = entry.get('content', {})
            text = polished or raw_xml or json.dumps(content, ensure_ascii=False, indent=2)
            parts.append(f"### [{role}] {round_label}\n{text}")
        return "\n\n".join(parts)

    # =========================================================================
    # 1. Init Nodes — 建立三辩论者对话线程
    # =========================================================================

    def _build_init_messages(self, agent: str, state: DebateState) -> List[Dict[str, str]]:
        """Z/R/F初始化：system=宪法+人设，user=格式+原始数据+初始任务"""
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
            "zealot_messages":    messages,
            "zealot_latest":      resp,
            "zealot_last_action": int(action) if isinstance(action, (int, float)) else 50,
        }

    def reaper_init_node(self, state: DebateState) -> Dict[str, Any]:
        logger.info("--- [Reaper] Initializing ---")
        messages = self._build_init_messages("reaper", state)
        resp = self.call_llm(messages, role="reaper")
        messages.append({"role": "assistant", "content": resp})

        output = self._parse_debate_output(resp, "reaper")
        action = output.get('action', 50)
        return {
            "reaper_messages":    messages,
            "reaper_latest":      resp,
            "reaper_last_action": int(action) if isinstance(action, (int, float)) else 50,
        }

    def fulcrum_init_node(self, state: DebateState) -> Dict[str, Any]:
        """Fulcrum现在是纯辩论者，只输出自己的立场；不再裁决、不再写batch"""
        logger.info("--- [Fulcrum] Initializing ---")
        messages = self._build_init_messages("fulcrum", state)
        resp = self.call_llm(messages, role="fulcrum")
        messages.append({"role": "assistant", "content": resp})

        output = self._parse_debate_output(resp, "fulcrum")
        action = output.get('action', 50)
        return {
            "fulcrum_messages":    messages,
            "fulcrum_latest":      resp,
            "fulcrum_last_action": int(action) if isinstance(action, (int, float)) else 50,
            "current_phase":       "moderation",
        }

    # =========================================================================
    # 2. Debate Nodes — 三辩论者平等
    # =========================================================================

    def _run_debate_round(self, agent: str, state: DebateState) -> Dict[str, Any]:
        """Z/R/F通用辩论逻辑；使用Chronicler精简后的记忆作为历史注入"""
        turn = state.get('turn_count', 1)
        logger.info(f"--- [{agent.capitalize()}] Round {turn} ---")

        messages_key = f"{agent}_messages"
        messages     = list(state[messages_key])
        output_format = self.pm.get_output_format(agent, "debate")
        symbol        = state.get('symbol', 'UNKNOWN')

        # 优先使用Chronicler精简后的历史，fallback到原始debate_history（兼容性兜底）
        history     = state.get('polished_debate_history', []) or state.get('debate_history', [])
        history_str = self._fmt_debate_batch(history) if history else "（无先前记录）"

        incremental_msg = (
            f"## 输出格式\n{output_format}\n\n"
            f"## 第{turn}轮辩论 | 标的：{symbol}\n\n"
            f"## 完整辩论记录\n{history_str}"
        )
        messages.append({"role": "user", "content": incremental_msg})
        resp = self.call_llm(messages, role=agent)
        messages.append({"role": "assistant", "content": resp})

        output = self._parse_debate_output(resp, agent)
        action = output.get('action', 50)
        return {
            messages_key:           messages,
            f"{agent}_latest":      resp,
            f"{agent}_last_action": int(action) if isinstance(action, (int, float)) else 50,
        }

    def zealot_debate_node(self, state: DebateState) -> Dict[str, Any]:
        return self._run_debate_round("zealot", state)

    def reaper_debate_node(self, state: DebateState) -> Dict[str, Any]:
        return self._run_debate_round("reaper", state)

    def fulcrum_debate_node(self, state: DebateState) -> Dict[str, Any]:
        """Fulcrum现在是普通辩论者，不再裁决、不再写batch"""
        return self._run_debate_round("fulcrum", state)

    # =========================================================================
    # 3. Chronicler Moderation — 秩序维护 + 记忆管理
    #
    #    在init阶段结束后 + 每轮debate结束后 被调用。
    #    负责：
    #      - 将本轮Z/R/F的XML归档到debate_history
    #      - 更新自己的messages线程（累积记忆）
    #      - 判定CONTINUE / TERMINATE
    #      - 决定下一轮turn_count
    # =========================================================================

    def chronicler_moderation_node(self, state: DebateState) -> Dict[str, Any]:
        turn = state.get('turn_count', 0)
        is_init_phase = (turn == 0)
        round_label   = "Init" if is_init_phase else f"回合{turn}"
        logger.info(f"--- [Chronicler] Moderation | {round_label} ---")

        zealot_xml  = state.get('zealot_latest', '')
        reaper_xml  = state.get('reaper_latest', '')
        fulcrum_xml = state.get('fulcrum_latest', '')

        # 解析三方原始发言供 debate_history 留档
        z_parsed = self._parse_debate_output(zealot_xml,  "zealot")
        r_parsed = self._parse_debate_output(reaper_xml,  "reaper")
        f_parsed = self._parse_debate_output(fulcrum_xml, "fulcrum")

        # 构建chronicler的messages线程（首次调用初始化system）
        messages = list(state.get('chronicler_messages', []))
        if not messages:
            system_content = self.pm.get_system_prompt("chronicler")
            messages.append({"role": "system", "content": system_content})

        output_format = self.pm.get_output_format("chronicler", "moderation")
        symbol        = state.get('symbol', 'UNKNOWN')
        round_xml_block = (
            f"[Zealot]\n{zealot_xml}\n\n"
            f"[Reaper]\n{reaper_xml}\n\n"
            f"[Fulcrum]\n{fulcrum_xml}"
        )
        task_msg = (
            f"## 秩序维护 | {round_label} 已结束\n"
            f"标的：{symbol}\n\n"
            f"## 本轮三方发言\n{round_xml_block}\n\n"
            f"## 输出格式\n{output_format}"
        )
        messages.append({"role": "user", "content": task_msg})
        resp = self.call_llm(messages, role="chronicler")
        messages.append({"role": "assistant", "content": resp})

        parsed   = self._parse_moderation(resp)
        decision = parsed["decision"]
        reason   = parsed["reason"]
        polished = parsed["polished"]

        # 硬保险：Init结束后强制CONTINUE至少1轮，Init不是辩论
        if is_init_phase and decision == "TERMINATE":
            logger.warning("[Chronicler] Post-init TERMINATE suppressed; forcing CONTINUE for at least one debate round.")
            decision = "CONTINUE"

        logger.info(f"[Chronicler] {round_label} decision: {decision} | {reason[:100]}")

        # debate_history：原始XML留档（用于最终JSON报告）
        batch_updates = [
            {"role": "Zealot",  "round": round_label, "content": z_parsed, "raw_xml": zealot_xml},
            {"role": "Reaper",  "round": round_label, "content": r_parsed, "raw_xml": reaper_xml},
            {"role": "Fulcrum", "round": round_label, "content": f_parsed, "raw_xml": fulcrum_xml},
        ]

        # polished_debate_history：Chronicler精简版，供下轮辩论者注入记忆
        # 若某方精简失败（polished为空），fallback到raw_xml保证完整性
        polished_updates = [
            {"role": "Zealot",  "round": round_label, "content": z_parsed,
             "polished_text": polished.get("zealot", "")  or zealot_xml},
            {"role": "Reaper",  "round": round_label, "content": r_parsed,
             "polished_text": polished.get("reaper", "")  or reaper_xml},
            {"role": "Fulcrum", "round": round_label, "content": f_parsed,
             "polished_text": polished.get("fulcrum", "") or fulcrum_xml},
        ]

        # 轮次递增：init→1，回合N→N+1
        next_turn = turn + 1

        return {
            "chronicler_messages":     messages,
            "debate_history":          batch_updates,
            "polished_debate_history": polished_updates,
            "debate_status":           decision,
            "turn_count":              next_turn,
            "current_phase":           "finalize" if decision == "TERMINATE" else "debate",
        }

    # =========================================================================
    # 4. Chronicler Finalize — 写最终报告
    # =========================================================================

    def chronicler_finalize_node(self, state: DebateState) -> Dict[str, Any]:
        logger.info("--- [Chronicler] Finalizing ---")

        messages      = list(state.get('chronicler_messages', []))
        if not messages:
            # 兜底：未被moderation过就直接finalize（理论不该发生）
            system_content = self.pm.get_system_prompt("chronicler")
            messages.append({"role": "system", "content": system_content})

        output_format = self.pm.get_output_format("chronicler", "finalize")
        symbol        = state.get('symbol', 'UNKNOWN')

        finalize_msg = (
            f"## 最终报告阶段 | 标的：{symbol}\n\n"
            f"辩论已结束。基于你在线程中旁听记录的完整辩论历程，请撰写最终裁决报告。\n\n"
            f"## 输出格式\n{output_format}"
        )
        messages.append({"role": "user", "content": finalize_msg})
        resp = self.call_llm(messages, role="chronicler")
        messages.append({"role": "assistant", "content": resp})

        output = self._parse_final_report(resp)
        report = output.get('final_report', output)

        return {
            "chronicler_messages": messages,
            "final_report":        report,
            "current_phase":       "signoff",
        }

    # =========================================================================
    # 5. Signoff Nodes — 三方对等签章
    # =========================================================================

    def _run_signoff(self, agent: str, state: DebateState) -> Dict[str, Any]:
        """Z/R/F通用签章逻辑"""
        logger.info(f"--- [{agent.capitalize()}] Signing off ---")

        messages_key     = f"{agent}_messages"
        messages         = list(state[messages_key])
        output_format    = self.pm.get_output_format(agent, "signoff")
        final_report_str = json.dumps(state.get('final_report', {}), ensure_ascii=False, indent=2)
        symbol           = state.get('symbol', 'UNKNOWN')

        # 签章阶段也用精简历史
        history     = state.get('polished_debate_history', []) or state.get('debate_history', [])
        history_str = self._fmt_debate_batch(history) if history else "（无记录）"

        signoff_msg = (
            f"## 完整辩论记录\n{history_str}\n\n"
            f"## 签章确认 | 标的：{symbol}\n\n"
            f"## 史官(Chronicler)最终裁决报告\n{final_report_str}\n\n"
            f"## 输出格式\n{output_format}"
        )
        messages.append({"role": "user", "content": signoff_msg})
        resp   = self.call_llm(messages, role=agent)
        output = self._parse_signoff(resp, agent)

        default_action = state.get(f"{agent}_last_action", 50)
        return {
            f"{agent}_signoff": {
                "final_action": output.get('final_action', default_action),
                "reservation":  output.get('reservation', ''),
            }
        }

    def zealot_signoff_node(self, state: DebateState) -> Dict[str, Any]:
        return self._run_signoff("zealot", state)

    def reaper_signoff_node(self, state: DebateState) -> Dict[str, Any]:
        return self._run_signoff("reaper", state)

    def fulcrum_signoff_node(self, state: DebateState) -> Dict[str, Any]:
        return self._run_signoff("fulcrum", state)

    # =========================================================================
    # 6. Data Saver
    # =========================================================================

    def data_saver_node(self, state: DebateState) -> Dict[str, Any]:
        logger.info("--- [System] Saving Data ---")
        final_json = state.get('final_report', {})
        if not final_json:
            logger.error("No final report to save!")
            return {}

        z_sig = state.get('zealot_signoff', {})  or {}
        r_sig = state.get('reaper_signoff', {})  or {}
        f_sig = state.get('fulcrum_signoff', {}) or {}

        # dissent 三方对等记录
        final_json['dissent'] = {
            "zealot_final_action":  z_sig.get('final_action', 50),
            "zealot_reservation":   z_sig.get('reservation', ''),
            "reaper_final_action":  r_sig.get('final_action', 50),
            "reaper_reservation":   r_sig.get('reservation', ''),
            "fulcrum_final_action": f_sig.get('final_action', 50),
            "fulcrum_reservation":  f_sig.get('reservation', ''),
        }

        final_json['signatures'] = self._get_model_signatures()

        final_json['debate_history'] = [
            {k: v for k, v in entry.items() if k != 'raw_xml'}
            for entry in state.get('debate_history', [])
        ]

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
