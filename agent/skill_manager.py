"""
Skill管理器 - 支持 Claude Code Skill 格式
支持技能配置管理：添加、启用、停用
"""

import os
import json
import shutil
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from .custom_types import Tool, ToolType, ToolResult
from .claude_code_skill import ClaudeCodeSkillParser, ClaudeCodeSkillExecutor


class SkillConfig:
    """技能配置类"""
    
    def __init__(self, name: str, enabled: bool = True, source_path: str = None, metadata: Dict = None):
        self.name = name
        self.enabled = enabled
        self.source_path = source_path or ""
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "source_path": self.source_path,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "SkillConfig":
        return cls(
            name=data.get("name", ""),
            enabled=data.get("enabled", True),
            source_path=data.get("source_path", ""),
            metadata=data.get("metadata", {})
        )


class SkillManager:
    """Skill管理器 - 支持 Claude Code Skill 和配置管理"""

    def __init__(self, skills_dir: str = "skills", config_dir: str = "config"):
        self.skills_dir = skills_dir
        self.config_dir = config_dir
        self.config_file = os.path.join(config_dir, "skills_config.json")
        self.tools: Dict[str, Tool] = {}
        self.claude_code_skills: Dict[str, Any] = {}  # name -> ClaudeCodeSkill
        self.skill_configs: Dict[str, SkillConfig] = {}  # name -> SkillConfig
        self.llm_client = None
        self.mcp_manager = None
        
    def set_dependencies(self, llm_client, mcp_manager):
        """设置依赖"""
        self.llm_client = llm_client
        self.mcp_manager = mcp_manager
        
    def load_config(self) -> None:
        """加载所有 Claude Code Skill"""
        # 首先加载技能配置
        self._load_skill_configs()
        # 然后加载启用的技能
        self._load_claude_code_skills()
        enabled_count = sum(1 for config in self.skill_configs.values() if config.enabled)
        print(f"共加载 {len(self.tools)} 个 Skill (总共 {len(self.skill_configs)} 个, 启用 {enabled_count} 个)")
    
    def _load_skill_configs(self):
        """加载技能配置文件"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    configs_data = json.load(f)
                for name, config_data in configs_data.items():
                    self.skill_configs[name] = SkillConfig.from_dict(config_data)
            except Exception as e:
                print(f"加载技能配置文件失败: {e}")
                self.skill_configs = {}

        # 扫描目录，自动添加未记录的技能
        if os.path.exists(self.skills_dir):
            for dir_name in os.listdir(self.skills_dir):
                skill_path = os.path.join(self.skills_dir, dir_name)
                skill_file = os.path.join(skill_path, "SKILL.md")

                # 跳过配置文件和特殊目录
                if dir_name.startswith("_") or dir_name.startswith("."):
                    continue
                if dir_name.endswith(".json"):
                    continue

                if os.path.isdir(skill_path) and os.path.exists(skill_file):
                    # 解析 SKILL.md 获取实际的 skill name
                    skill = ClaudeCodeSkillParser.parse_skill_md(skill_path)
                    actual_name = skill.name if skill else dir_name

                    if actual_name not in self.skill_configs:
                        # 自动添加新发现的技能，默认启用
                        self.skill_configs[actual_name] = SkillConfig(
                            name=actual_name,
                            enabled=True,
                            source_path=skill_path
                        )
                        self._save_skill_configs()
    
    def _save_skill_configs(self):
        """保存技能配置到文件"""
        try:
            configs_data = {name: config.to_dict() for name, config in self.skill_configs.items()}
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(configs_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存技能配置文件失败: {e}")
    
    def _load_claude_code_skills(self):
        """加载 Claude Code Skill"""
        if not os.path.exists(self.skills_dir):
            print(f"Skill 目录不存在: {self.skills_dir}")
            return

        for dir_name in os.listdir(self.skills_dir):
            skill_path = os.path.join(self.skills_dir, dir_name)
            skill_file = os.path.join(skill_path, "SKILL.md")

            # 跳过配置文件和特殊目录
            if dir_name.startswith("_") or dir_name.startswith("."):
                continue
            if dir_name.endswith(".json"):
                continue

            if os.path.isdir(skill_path) and os.path.exists(skill_file):
                # 解析 SKILL.md 获取实际的 skill name
                skill = ClaudeCodeSkillParser.parse_skill_md(skill_path)
                if not skill:
                    continue

                actual_name = skill.name

                # 检查技能是否被启用（使用实际的 skill name）
                config = self.skill_configs.get(actual_name)
                if config and not config.enabled:
                    continue  # 跳过禁用的技能

                self.claude_code_skills[actual_name] = skill

                # 创建工具定义
                self.tools[actual_name] = Tool(
                    name=actual_name,
                    description=f"Claude Code Skill: {actual_name}",
                    type=ToolType.SKILL,
                    parameters={"arguments": {"type": "string", "description": "Skill 参数"}},
                    handler=None,
                    config={"type": "claude_code", "skill": skill}
                )

                print(f"已加载 Skill: {actual_name}")
    
    def add_skill(self, source_dir: str, skill_name: str = None) -> Tuple[bool, str]:
        """
        添加新的 Skill
        
        Args:
            source_dir: 源 Skill 目录路径
            skill_name: 目标 Skill 名称（可选，默认使用源目录名）
            
        Returns:
            (成功标志, 消息)
        """
        source_path = Path(source_dir)
        
        # 检查源目录是否存在
        if not source_path.exists():
            return False, f"源目录不存在: {source_dir}"
        
        if not source_path.is_dir():
            return False, f"源路径不是目录: {source_dir}"
        
        # 检查 SKILL.md 文件是否存在
        skill_md = source_path / "SKILL.md"
        if not skill_md.exists():
            return False, f"源目录缺少 SKILL.md 文件: {source_dir}"
        
        # 确定技能名称
        if not skill_name:
            skill_name = source_path.name
        
        # 检查目标目录是否已存在
        target_path = Path(self.skills_dir) / skill_name
        if target_path.exists():
            return False, f"Skill '{skill_name}' 已存在"
        
        try:
            # 复制目录
            shutil.copytree(source_path, target_path)
            
            # 添加到配置
            self.skill_configs[skill_name] = SkillConfig(
                name=skill_name,
                enabled=True,
                source_path=str(source_path)
            )
            self._save_skill_configs()
            
            # 尝试加载新技能
            skill = ClaudeCodeSkillParser.parse_skill_md(str(target_path))
            if skill:
                self.claude_code_skills[skill.name] = skill
                self.tools[skill.name] = Tool(
                    name=skill.name,
                    description=f"Claude Code Skill: {skill.name}",
                    type=ToolType.SKILL,
                    parameters={"arguments": {"type": "string", "description": "Skill 参数"}},
                    handler=None,
                    config={"type": "claude_code", "skill": skill}
                )
            
            return True, f"Skill '{skill_name}' 添加成功"
            
        except Exception as e:
            # 清理已复制的文件
            if target_path.exists():
                shutil.rmtree(target_path)
            return False, f"添加 Skill 失败: {str(e)}"
    
    def remove_skill(self, skill_name: str) -> Tuple[bool, str]:
        """
        删除 Skill
        
        Args:
            skill_name: Skill 名称
            
        Returns:
            (成功标志, 消息)
        """
        if skill_name not in self.skill_configs:
            return False, f"Skill '{skill_name}' 不存在"
        
        skill_path = Path(self.skills_dir) / skill_name
        
        try:
            # 删除目录
            if skill_path.exists():
                shutil.rmtree(skill_path)
            
            # 从配置中移除
            del self.skill_configs[skill_name]
            self._save_skill_configs()
            
            # 从已加载的技能中移除
            if skill_name in self.claude_code_skills:
                del self.claude_code_skills[skill_name]
            if skill_name in self.tools:
                del self.tools[skill_name]
            
            return True, f"Skill '{skill_name}' 已删除"
            
        except Exception as e:
            return False, f"删除 Skill 失败: {str(e)}"
    
    def enable_skill(self, skill_name: str) -> Tuple[bool, str]:
        """
        启用 Skill
        
        Args:
            skill_name: Skill 名称
            
        Returns:
            (成功标志, 消息)
        """
        if skill_name not in self.skill_configs:
            return False, f"Skill '{skill_name}' 不存在"
        
        config = self.skill_configs[skill_name]
        if config.enabled:
            return True, f"Skill '{skill_name}' 已经是启用状态"
        
        config.enabled = True
        self._save_skill_configs()
        
        # 重新加载技能
        skill_path = Path(self.skills_dir) / skill_name
        skill = ClaudeCodeSkillParser.parse_skill_md(str(skill_path))
        if skill:
            self.claude_code_skills[skill.name] = skill
            self.tools[skill.name] = Tool(
                name=skill.name,
                description=f"Claude Code Skill: {skill.name}",
                type=ToolType.SKILL,
                parameters={"arguments": {"type": "string", "description": "Skill 参数"}},
                handler=None,
                config={"type": "claude_code", "skill": skill}
            )
        
        return True, f"Skill '{skill_name}' 已启用"
    
    def disable_skill(self, skill_name: str) -> Tuple[bool, str]:
        """
        停用 Skill
        
        Args:
            skill_name: Skill 名称
            
        Returns:
            (成功标志, 消息)
        """
        if skill_name not in self.skill_configs:
            return False, f"Skill '{skill_name}' 不存在"
        
        config = self.skill_configs[skill_name]
        if not config.enabled:
            return True, f"Skill '{skill_name}' 已经是停用状态"
        
        config.enabled = False
        self._save_skill_configs()
        
        # 从已加载的技能中移除
        if skill_name in self.claude_code_skills:
            del self.claude_code_skills[skill_name]
        if skill_name in self.tools:
            del self.tools[skill_name]
        
        return True, f"Skill '{skill_name}' 已停用"
    
    def list_skills(self) -> List[Dict[str, Any]]:
        """
        列出所有 Skill
        
        Returns:
            Skill 列表，包含名称、状态等信息
        """
        result = []
        for name, config in self.skill_configs.items():
            skill_info = {
                "name": name,
                "enabled": config.enabled,
                "loaded": name in self.tools,
                "source_path": config.source_path
            }
            result.append(skill_info)
        return result
    
    def get_skill_status(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """
        获取 Skill 状态

        Args:
            skill_name: Skill 名称

        Returns:
            Skill 状态信息，如果不存在返回 None
        """
        if skill_name not in self.skill_configs:
            return None

        config = self.skill_configs[skill_name]
        return {
            "name": skill_name,
            "enabled": config.enabled,
            "loaded": skill_name in self.tools,
            "source_path": config.source_path,
            "metadata": config.metadata
        }
    
    def get_tools(self) -> List[Tool]:
        """获取所有可用的 Skill 工具"""
        return list(self.tools.values())
    
    def get_tool(self, name: str) -> Optional[Tool]:
        """获取指定工具"""
        return self.tools.get(name)
    
    async def call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        """调用 Skill 工具"""
        if tool_name not in self.tools:
            return ToolResult(success=False, data=None, error=f"Skill 工具 '{tool_name}' 不存在")
        
        tool = self.tools[tool_name]
        
        # 调用 Claude Code Skill
        if tool.config and tool.config.get("type") == "claude_code":
            return await self._call_claude_code_skill(tool_name, parameters)
        
        return ToolResult(success=False, data=None, error=f"Skill '{tool_name}' 类型不支持")
    
    async def _call_claude_code_skill(self, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        """调用 Claude Code Skill"""
        if not self.llm_client or not self.mcp_manager:
            return ToolResult(success=False, data=None, error="Claude Code Skill 需要 LLM 和 MCP 管理器")
        
        skill = self.claude_code_skills.get(tool_name)
        if not skill:
            return ToolResult(success=False, data=None, error=f"Claude Code Skill '{tool_name}' 未找到")
        
        try:
            executor = ClaudeCodeSkillExecutor(self.llm_client, self.mcp_manager)
            arguments = parameters.get("arguments", "")
            result = await executor.execute(skill, arguments)
            
            return ToolResult(success=True, data=result)
            
        except Exception as e:
            return ToolResult(success=False, data=None, error=f"Claude Code Skill 执行失败: {str(e)}")
