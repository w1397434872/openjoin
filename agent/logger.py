"""
日志记录模块 - 记录完整的对话和工具返回结果
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path


class AgentLogger:
    """智能体日志记录器"""

    def __init__(self, log_dir: str = "log"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

        # 创建日志文件路径
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"session_{self.session_id}.log"
        self.tool_results_file = self.log_dir / f"tool_results_{self.session_id}.jsonl"

        # 初始化日志
        self._init_log()

    def _init_log(self):
        """初始化日志文件"""
        self.info(f"=" * 80)
        self.info(f"智能体会话开始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.info(f"=" * 80)

    def _write_log(self, level: str, message: str):
        """写入日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_line = f"[{timestamp}] [{level}] {message}\n"

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_line)

    def info(self, message: str):
        """记录信息日志"""
        self._write_log("INFO", message)

    def debug(self, message: str):
        """记录调试日志"""
        self._write_log("DEBUG", message)

    def error(self, message: str):
        """记录错误日志"""
        self._write_log("ERROR", message)

    def log_user_input(self, user_input: str):
        """记录用户输入"""
        self.info(f"用户输入: {user_input}")

    def log_thought(self, step: int, thought: str):
        """记录思考过程"""
        self.info(f"步骤 {step} - 思考: {thought}")

    def log_action(self, step: int, tool_name: str, parameters: Dict):
        """记录工具调用"""
        self.info(f"步骤 {step} - 调用工具: {tool_name}")
        self.info(f"步骤 {step} - 参数: {json.dumps(parameters, ensure_ascii=False)}")

    def log_tool_result(self, step: int, tool_name: str, result: Any, success: bool):
        """
        记录工具返回结果（完整不截断）

        Args:
            step: 步骤编号
            tool_name: 工具名称
            result: 工具返回结果
            success: 是否成功
        """
        # 记录到文本日志
        status = "成功" if success else "失败"
        self.info(f"步骤 {step} - 工具 {tool_name} 执行{status}")

        # 将完整结果记录到 JSONL 文件
        result_entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "step": step,
            "tool_name": tool_name,
            "success": success,
            "result": result
        }

        with open(self.tool_results_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(result_entry, ensure_ascii=False) + "\n")

        # 同时在主日志中记录结果摘要
        if isinstance(result, (dict, list)):
            result_str = json.dumps(result, ensure_ascii=False, indent=2)
        else:
            result_str = str(result)

        # 记录结果长度信息
        self.info(f"步骤 {step} - 结果长度: {len(result_str)} 字符")
        self.info(f"步骤 {step} - 完整结果已保存到: {self.tool_results_file}")

    def log_final_answer(self, answer: str):
        """记录最终答案"""
        self.info(f"最终答案: {answer}")

    def log_error(self, error: str):
        """记录错误"""
        self.error(f"错误: {error}")

    def log_separator(self, char: str = "-", length: int = 80):
        """记录分隔线"""
        self.info(char * length)

    def get_log_files(self) -> Dict[str, str]:
        """获取日志文件路径"""
        return {
            "log_file": str(self.log_file),
            "tool_results": str(self.tool_results_file)
        }

    def close(self):
        """关闭日志会话"""
        self.info(f"=" * 80)
        self.info(f"智能体会话结束 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.info(f"=" * 80)


# 全局日志实例
_global_logger: Optional[AgentLogger] = None


def get_logger(log_dir: str = "log") -> AgentLogger:
    """获取全局日志实例"""
    global _global_logger
    if _global_logger is None:
        _global_logger = AgentLogger(log_dir)
    return _global_logger


def reset_logger():
    """重置日志实例"""
    global _global_logger
    if _global_logger:
        _global_logger.close()
    _global_logger = None
