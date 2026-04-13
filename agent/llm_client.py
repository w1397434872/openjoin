"""
LLM客户端 - 使用OpenAI API
"""

import os
import json
from typing import Any, Dict, List, Optional, AsyncGenerator, Tuple
from openai import AsyncOpenAI
from dotenv import load_dotenv

from .custom_types import Message, Tool, ToolCall, ToolType


class TokenUsage:
    """Token 使用统计"""
    def __init__(self):
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
    
    def add(self, usage):
        """添加使用量"""
        if usage:
            self.prompt_tokens += usage.prompt_tokens or 0
            self.completion_tokens += usage.completion_tokens or 0
            self.total_tokens += usage.total_tokens or 0
    
    def to_dict(self) -> Dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens
        }


class LLMClient:
    """OpenAI LLM客户端"""
    
    def __init__(self):
        # 加载环境变量
        load_dotenv()
        
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.base_url = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
        self.model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
        self.temperature = float(os.getenv('OPENAI_TEMPERATURE', '0.7'))
        self.max_tokens = int(os.getenv('OPENAI_MAX_TOKENS', '4096'))
        
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY 未设置，请在.env文件中配置")
        
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    def _build_system_prompt(self, tools: List[Tool]) -> str:
        """构建系统提示词"""
        tool_descriptions = []
        for tool in tools:
            desc = f"""
工具名称: {tool.name}
类型: {tool.type.value}
"""
            # 如果是 Claude Code Skill，添加 frontmatter
            if tool.config and tool.config.get("type") == "claude_code":
                skill = tool.config.get("skill")
                if skill:
                    desc += f"""
【Skill 定义】
{skill.frontmatter}
"""
            else:
                # 其他工具使用传统描述
                desc += f"""
描述: {tool.description}
参数: {json.dumps(tool.parameters, ensure_ascii=False)}
"""
            
            tool_descriptions.append(desc)
        
        tools_text = "\n".join(tool_descriptions) if tool_descriptions else "无可用工具"
        
        return f"""你是一个智能助手，可以使用以下工具来帮助用户完成任务。

可用工具:
{tools_text}

请使用ReAct模式（思考-行动-观察）来解决问题：
1. Thought: 分析当前情况，决定下一步行动
2. Action: 如果需要使用工具，输出JSON格式的工具调用
3. Observation: 观察工具返回的结果
4. 重复以上步骤直到完成任务

当你需要调用工具时，请使用以下格式输出：
```action
{{"tool": "工具名称", "parameters": {{"参数名": "参数值"}}}}
```

当你完成任务时，请输出：
```final
最终答案
```

重要提示：
- 当工具返回列表或结构化数据时，请以**结构化格式**（表格/列表）完整展示，不要只给摘要
- 包含所有关键字段，确保信息完整、清晰、易读
- 使用 Markdown 格式（表格、列表、代码块等）提升可读性
- 如果数据量大，优先展示最重要的信息，但需说明完整数据情况

请始终保持这个格式，这对我很重要。
"""
    
    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """转换消息格式"""
        openai_messages = []
        for msg in messages:
            openai_msg = {
                "role": msg.role,
                "content": msg.content
            }
            openai_messages.append(openai_msg)
        return openai_messages
    
    async def chat(self, messages: List[Message], tools: List[Tool] = None) -> Tuple[str, TokenUsage]:
        """
        与LLM对话
        
        Returns:
            (回复内容, Token使用量)
        """
        # 构建系统消息
        system_prompt = self._build_system_prompt(tools or [])

        # 构建消息列表
        openai_messages = [{"role": "system", "content": system_prompt}]
        openai_messages.extend(self._convert_messages(messages))

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )

            # 获取 token 使用量
            usage = TokenUsage()
            usage.add(response.usage)

            return response.choices[0].message.content, usage

        except Exception as e:
            raise Exception(f"LLM调用失败: {str(e)}")
    
    async def chat_stream(self, messages: List[Message], tools: List[Tool] = None) -> AsyncGenerator[str, None]:
        """流式对话"""
        system_prompt = self._build_system_prompt(tools or [])
        
        openai_messages = [{"role": "system", "content": system_prompt}]
        openai_messages.extend(self._convert_messages(messages))
        
        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=True
            )
            
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            raise Exception(f"LLM流式调用失败: {str(e)}")
    
    def parse_action(self, content: str) -> Optional[ToolCall]:
        """从LLM输出中解析工具调用"""
        import re
        
        # 匹配 action 代码块
        action_pattern = r'```action\s*(.*?)\s*```'
        match = re.search(action_pattern, content, re.DOTALL)
        
        if match:
            try:
                action_json = match.group(1).strip()
                action_data = json.loads(action_json)
                
                tool_name = action_data.get('tool')
                parameters = action_data.get('parameters', {})
                
                # 判断工具类型
                tool_type = ToolType.MCP  # 默认MCP
                
                return ToolCall(
                    tool_name=tool_name,
                    parameters=parameters,
                    tool_type=tool_type
                )
            except json.JSONDecodeError:
                return None
        
        return None
    
    def parse_final_answer(self, content: str) -> Optional[str]:
        """从LLM输出中解析最终答案"""
        import re
        
        # 匹配 final 代码块（支持 ```final 和 ``` final 两种格式）
        final_pattern = r'```\s*final\s*\n?(.*?)```'
        match = re.search(final_pattern, content, re.DOTALL)
        
        if match:
            return match.group(1).strip()
        
        # 备用：检查是否包含 "最终答案" 或 "Final Answer" 标记
        if "最终答案" in content and len(content) > 20:
            # 提取 "最终答案" 后的内容
            idx = content.find("最终答案")
            return content[idx:].strip()
        
        return None
    
    def is_final_answer(self, content: str) -> bool:
        """检查是否是最终答案"""
        return "```final" in content or "最终答案" in content
