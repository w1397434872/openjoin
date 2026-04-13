"""
类型定义
"""

from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum


class ToolType(Enum):
    MCP = "mcp"
    SKILL = "skill"


@dataclass
class Tool:
    """工具定义"""
    name: str
    description: str
    type: ToolType
    parameters: Dict[str, Any] = field(default_factory=dict)
    required_params: List[str] = field(default_factory=list)
    handler: Optional[Callable] = None
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    """工具调用"""
    tool_name: str
    parameters: Dict[str, Any]
    tool_type: ToolType


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    data: Any
    error: Optional[str] = None


@dataclass
class Message:
    """对话消息"""
    role: str  # system, user, assistant, tool
    content: str
    tool_calls: Optional[List[ToolCall]] = None
    tool_results: Optional[List[ToolResult]] = None


@dataclass
class Thought:
    """思考记录"""
    step: int
    thought: str
    is_final: bool = False
    action: Optional[ToolCall] = None
    observation: Optional[str] = None
