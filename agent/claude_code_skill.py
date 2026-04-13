"""
Claude Code Skill 支持模块
简化版本：只读取 frontmatter，让大模型自己读取完整内容
"""

import os
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ClaudeCodeSkill:
    """Claude Code Skill 定义 - 简化版"""
    name: str
    frontmatter: str  # 完整的 frontmatter 文本
    skill_dir: str    # Skill 目录路径


class ClaudeCodeSkillParser:
    """Claude Code Skill 解析器 - 简化版"""
    
    @staticmethod
    def parse_skill_md(skill_path: str) -> Optional[ClaudeCodeSkill]:
        """解析 SKILL.md 文件，只提取 frontmatter"""
        skill_file = Path(skill_path) / "SKILL.md"
        if not skill_file.exists():
            return None
        
        with open(skill_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 解析 YAML frontmatter（允许前面有空白字符）
        frontmatter_match = re.search(r'---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
        if not frontmatter_match:
            return None
        
        frontmatter = frontmatter_match.group(1).strip()
        
        # 提取 name 字段（用于标识）
        name_match = re.search(r'^name:\s*(.+)$', frontmatter, re.MULTILINE)
        name = name_match.group(1).strip() if name_match else Path(skill_path).name
        
        return ClaudeCodeSkill(
            name=name,
            frontmatter=frontmatter,
            skill_dir=skill_path
        )


class SkillDirectoryReader:
    """Skill 目录读取器 - 供大模型使用"""
    
    @staticmethod
    def read_skill_directory(skill_dir: str) -> Dict[str, Any]:
        """
        读取整个 Skill 目录的内容
        返回包含所有文件内容的字典
        """
        result = {
            "skill_dir": skill_dir,
            "files": {},
            "workflows": {}
        }
        
        skill_path = Path(skill_dir)
        if not skill_path.exists():
            return {"error": f"Skill 目录不存在: {skill_dir}"}
        
        # 读取主文件 SKILL.md
        skill_md = skill_path / "SKILL.md"
        if skill_md.exists():
            with open(skill_md, 'r', encoding='utf-8') as f:
                result["files"]["SKILL.md"] = f.read()
        
        # 读取 workflows 目录
        workflows_dir = skill_path / "workflows"
        if workflows_dir.exists():
            for workflow_file in workflows_dir.glob("*.md"):
                with open(workflow_file, 'r', encoding='utf-8') as f:
                    result["workflows"][workflow_file.name] = f.read()
        
        # 读取其他参考文件
        reference_dir = skill_path / "reference"
        if reference_dir.exists():
            for ref_file in reference_dir.glob("*.md"):
                with open(ref_file, 'r', encoding='utf-8') as f:
                    result["files"][f"reference/{ref_file.name}"] = f.read()
        
        return result
    
    @staticmethod
    def format_skill_for_llm(skill_data: Dict[str, Any]) -> str:
        """将 Skill 数据格式化为大模型可读的文本"""
        if "error" in skill_data:
            return f"错误: {skill_data['error']}"
        
        parts = []
        parts.append(f"=== Skill 目录: {skill_data['skill_dir']} ===\n")
        
        # 主文件
        if "SKILL.md" in skill_data["files"]:
            parts.append("【SKILL.md】")
            parts.append(skill_data["files"]["SKILL.md"])
            parts.append("")
        
        # 工作流
        if skill_data["workflows"]:
            parts.append("【Workflows】")
            for name, content in skill_data["workflows"].items():
                parts.append(f"\n--- {name} ---")
                parts.append(content)
            parts.append("")
        
        # 参考文件
        other_files = {k: v for k, v in skill_data["files"].items() if k != "SKILL.md"}
        if other_files:
            parts.append("【参考文件】")
            for name, content in other_files.items():
                parts.append(f"\n--- {name} ---")
                parts.append(content)
        
        return "\n".join(parts)


class ClaudeCodeSkillExecutor:
    """Claude Code Skill 执行器 - 简化版"""
    
    def __init__(self, llm_client, mcp_manager):
        self.llm = llm_client
        self.mcp = mcp_manager
    
    async def execute(self, skill: ClaudeCodeSkill, arguments: str) -> Dict[str, Any]:
        """执行 Skill"""
        # 读取完整的 Skill 目录
        skill_data = SkillDirectoryReader.read_skill_directory(skill.skill_dir)
        skill_content = SkillDirectoryReader.format_skill_for_llm(skill_data)

        # 构建系统提示
        system_prompt = f"""你是一个 {skill.name} Skill 执行助手。

以下是完整的 Skill 定义和工作流程：

{skill_content}

你的任务是根据上述 Skill 定义，执行用户的请求。
请仔细阅读工作流，按照步骤执行。
允许使用的工具由 Skill 定义中的 allowed-tools 指定。
"""

        # 构建用户输入
        user_input = f"执行请求: {arguments}\n\n请按照上述 Skill 定义执行此任务。"

        # 调用 LLM 执行（使用简单调用，不通过 ReAct 循环）
        from .custom_types import Message
        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_input)
        ]

        response, token_usage = await self.llm.chat(messages)

        return {
            "success": True,
            "result": response,
            "skill": skill.name,
            "token_usage": token_usage.to_dict()
        }
