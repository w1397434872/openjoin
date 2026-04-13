"""
智能体主类 - 整合所有组件
"""

import asyncio
import os
from typing import List, Optional, Callable
from dotenv import load_dotenv
from .custom_types import Thought
from .llm_client import LLMClient
from .mcp_manager import MCPManager
from .skill_manager import SkillManager
from .react_loop import ReActLoop

# 加载环境变量
load_dotenv()


class Agent:
    """
    智能体 - 支持MCP和Skill的ReAct智能体

    使用方法:
        agent = Agent()
        await agent.initialize()
        result = await agent.run("你的问题")
    """

    def __init__(
        self,
        mcp_config_path: str = "config/mcp_config.json",
        skills_dir: str = "skills",
        skills_config_dir: str = "config",
        enable_memory: bool = None,
        enable_vector_memory: bool = None,
        milvus_host: str = None,
        milvus_port: str = None,
        enable_logging: bool = True
    ):
        self.mcp_config_path = mcp_config_path
        self.skills_dir = skills_dir
        self.skills_config_dir = skills_config_dir

        # 从环境变量读取配置
        if enable_memory is None:
            enable_memory = os.getenv("ENABLE_MEMORY", "true").lower() in ("true", "1", "yes")
        self.enable_memory = enable_memory

        if enable_vector_memory is None:
            enable_vector_memory = os.getenv("ENABLE_VECTOR_MEMORY", "true").lower() in ("true", "1", "yes")
        self.enable_vector_memory = enable_vector_memory

        self.milvus_host = milvus_host or os.getenv("MILVUS_HOST", "localhost")
        self.milvus_port = milvus_port or os.getenv("MILVUS_PORT", "19530")
        self.enable_logging = enable_logging

        # 组件
        self.llm: Optional[LLMClient] = None
        self.mcp: Optional[MCPManager] = None
        self.skill: Optional[SkillManager] = None
        self.react: Optional[ReActLoop] = None

        self._initialized = False
    
    async def initialize(self):
        """初始化智能体（异步）"""
        if self._initialized:
            return
        
        print("初始化智能体...")
        
        # 初始化LLM客户端
        print("  连接LLM...")
        self.llm = LLMClient()
        
        # 初始化MCP管理器
        print("  加载MCP工具...")
        self.mcp = MCPManager(self.mcp_config_path)
        await self.mcp.load_config()
        
        # 初始化Skill管理器 (Claude Code Skill)
        print("  加载Skill工具...")
        self.skill = SkillManager(self.skills_dir, self.skills_config_dir)
        self.skill.set_dependencies(self.llm, self.mcp)
        self.skill.load_config()
        
        # 初始化ReAct循环
        self.react = ReActLoop(
            llm_client=self.llm,
            mcp_manager=self.mcp,
            skill_manager=self.skill,
            enable_memory=self.enable_memory,
            enable_vector_memory=self.enable_vector_memory,
            milvus_host=self.milvus_host,
            milvus_port=self.milvus_port,
            enable_logging=self.enable_logging
        )

        self._initialized = True
        print("智能体初始化完成")
        if self.enable_logging:
            print("  日志记录已启用，日志保存在 log/ 目录")

    def initialize_sync(self):
        """同步初始化（用于非异步环境）"""
        if self._initialized:
            return

        print("初始化智能体...")

        # 初始化LLM客户端
        print("  连接LLM...")
        self.llm = LLMClient()

        # 初始化MCP管理器（异步转同步）
        print("  加载MCP工具...")
        self.mcp = MCPManager(self.mcp_config_path)
        try:
            asyncio.run(self.mcp.load_config())
        except Exception as e:
            print(f"  MCP加载失败: {e}")

        # 初始化Skill管理器
        print("  加载Skill工具...")
        self.skill = SkillManager(self.skills_dir, self.skills_config_dir)
        self.skill.load_config()

        # 初始化ReAct循环
        self.react = ReActLoop(
            llm_client=self.llm,
            mcp_manager=self.mcp,
            skill_manager=self.skill,
            enable_memory=self.enable_memory,
            enable_vector_memory=self.enable_vector_memory,
            milvus_host=self.milvus_host,
            milvus_port=self.milvus_port,
            enable_logging=self.enable_logging
        )

        self._initialized = True
        print("智能体初始化完成")
    
    async def run(self, user_input: str) -> str:
        """
        运行智能体处理用户输入
        
        Args:
            user_input: 用户输入
            
        Returns:
            智能体的回答
        """
        if not self._initialized:
            await self.initialize()
        
        return await self.react.run(user_input)
    
    async def chat(self, message: str) -> str:
        """简化的对话接口"""
        return await self.run(message)
    
    def get_available_tools(self) -> List[dict]:
        """获取所有可用工具"""
        if not self._initialized:
            self.initialize_sync()
        
        tools = []
        
        # MCP工具
        for tool in self.mcp.get_tools():
            tools.append({
                "name": tool.name,
                "type": "MCP",
                "description": tool.description
            })
        
        # Skill工具
        for tool in self.skill.get_tools():
            tools.append({
                "name": tool.name,
                "type": "Skill",
                "description": tool.description
            })
        
        return tools
    
    def get_history(self) -> List[Thought]:
        """获取对话历史"""
        if self.react:
            return self.react.get_history()
        return []
    
    def clear_history(self):
        """清除对话历史"""
        if self.react:
            self.react.clear_history()
    
    def get_memory_stats(self) -> dict:
        """获取 memory 统计信息"""
        if self.react:
            return self.react.get_memory_stats()
        return {}
    
    async def cleanup_async(self):
        """异步清理资源"""
        if self.mcp:
            await self.mcp.cleanup_async()
        self._initialized = False
    
    def cleanup(self):
        """同步清理资源"""
        if self.mcp:
            self.mcp.cleanup()
        self._initialized = False
