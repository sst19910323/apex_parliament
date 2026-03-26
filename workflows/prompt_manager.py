# -----------------------------------------------------------------
# 文件路径: workflows/prompt_manager.py
# (V9 - 重构：适配新架构 constitution/formats/tasks)
# -----------------------------------------------------------------
import yaml
import logging
import re
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

class PromptManager:
    def __init__(self, base_dir="prompts"):
        self.base_path = Path(base_dir)
        if not self.base_path.exists():
            self.base_path = Path(__file__).parent.parent / "prompts"
            
        self.prompts: Dict[str, Any] = {
            "constitution": {},  # shared_rules + 三方soul
            "formats": {},       # debate_output + final_report_output
            "tasks": {}          # task.yaml
        }
        self._load_all_prompts()

    def _load_all_prompts(self):
        try:
            # 1. Load Constitution (shared_rules + souls)
            constitution_dir = self.base_path / "constitution"
            if constitution_dir.exists():
                for f in constitution_dir.glob("*.yaml"):
                    with f.open('r', encoding='utf-8') as file:
                        content = yaml.safe_load(file)
                        if content:
                            # 文件名作为key，如 shared_rules, zealot_soul, etc.
                            self.prompts["constitution"][f.stem] = content
            
            # 2. Load Formats (output formats)
            formats_dir = self.base_path / "formats"
            if formats_dir.exists():
                for f in formats_dir.glob("*.yaml"):
                    with f.open('r', encoding='utf-8') as file:
                        content = yaml.safe_load(file)
                        if content:
                            self.prompts["formats"][f.stem] = content

            # 3. Load Tasks
            tasks_dir = self.base_path / "tasks"
            if tasks_dir.exists():
                for f in tasks_dir.glob("*.yaml"):
                    with f.open('r', encoding='utf-8') as file:
                        content = yaml.safe_load(file)
                        if content:
                            self.prompts["tasks"][f.stem] = content
            
            logger.info(f"✅ PromptManager Ready (V9)")
            
        except Exception as e:
            logger.error(f"❌ Prompt Load Error: {e}", exc_info=True)

    def get_system_prompt(self, agent: str) -> str:
        """
        组装System Prompt = shared_rules + agent_soul
        agent: zealot / reaper / fulcrum
        """
        shared_rules = self.prompts["constitution"].get("shared_rules", {}).get("shared_rules", "")
        soul_key = f"{agent}_soul"
        soul = self.prompts["constitution"].get(soul_key, {}).get(f"{soul_key}", "")
        
        if not soul:
            logger.warning(f"⚠️ Soul not found for agent: {agent}")
            return shared_rules
        
        return f"{shared_rules}\n\n{soul}"

    def get_output_format(self, agent: str, phase: str) -> str:
        """
        获取输出格式
        agent: zealot / reaper / fulcrum
        phase: init / debate / finalize / signoff
        """
        formats = self.prompts["formats"]
        
        if phase == "init":
            # 三方共用init_output
            return formats.get("debate_output", {}).get("init_output", "")
        
        elif phase == "debate":
            # 各自的debate输出
            key = f"{agent}_debate_output"
            return formats.get("debate_output", {}).get(key, "")
        
        elif phase == "finalize":
            # Fulcrum专用
            return formats.get("final_report_output", {}).get("final_report_output", "")
        
        elif phase == "signoff":
            # Zealot和Reaper签章
            return formats.get("final_report_output", {}).get("signoff_output", "")
        
        return ""

    def get_task_prompt(self, phase: str, task_type: str, data: Dict[str, Any]) -> str:
        """
        获取任务指令并填充数据
        phase: init / debate / finalize / signoff
        task_type: stock / etf / general
        data: 包含symbol, raw_data, debate_history, turn, final_report等
        """
        tasks = self.prompts["tasks"].get("task", {})
        
        # 1. 获取task模板
        task_key = f"{phase}_task"
        task_template = tasks.get(task_key, "")
        if not task_template:
            return f"[Error: Task '{task_key}' not found]"
        
        # 2. 获取raw_data模板（如果需要）
        if phase in ["init", "debate", "finalize"] and "raw_data" not in data:
            raw_data_key = f"raw_data_{task_type}"
            raw_data_template = tasks.get(raw_data_key, "")
            if raw_data_template:
                data["raw_data"] = self._regex_format(raw_data_template, data)
        
        # 3. 填充数据
        return self._regex_format(task_template, data)

    def build_full_prompt(self, agent: str, phase: str, task_type: str, data: Dict[str, Any]) -> Dict[str, str]:
        """
        构建完整的prompt
        返回: {"system": system_prompt, "user": user_prompt}
        """
        # System = shared_rules + soul + output_format
        system_prompt = self.get_system_prompt(agent)
        output_format = self.get_output_format(agent, phase)
        if output_format:
            system_prompt += f"\n\n## 输出格式\n{output_format}"
        
        # User = task + data
        user_prompt = self.get_task_prompt(phase, task_type, data)
        
        return {
            "system": system_prompt,
            "user": user_prompt
        }

    def _regex_format(self, template: str, data: Dict[str, Any]) -> str:
        def replace_match(match):
            key = match.group(1)
            if key in data:
                val = data[key]
                if isinstance(val, (dict, list)):
                    return str(val)
                return str(val)
            return match.group(0)

        pattern = re.compile(r'\{([a-zA-Z0-9_]+)\}')
        try:
            return pattern.sub(replace_match, template)
        except Exception as e:
            logger.error(f"Regex Format Error: {e}")
            return template