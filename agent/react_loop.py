"""
ReAct推理循环 - 实现思考-行动-观察循环
"""

import json
import os
from typing import List, Optional, Callable, Dict, Any
from .custom_types import Message, Thought, ToolCall, ToolResult, ToolType
from .llm_client import LLMClient, TokenUsage
from .mcp_manager import MCPManager
from .skill_manager import SkillManager
from .memory import MemoryManager
from .vector_memory import VectorMemoryManager
from .logger import get_logger


class ReActLoop:
    """ReAct推理循环"""

    def __init__(
        self,
        llm_client: LLMClient,
        mcp_manager: MCPManager,
        skill_manager: SkillManager,
        max_iterations: int = 10,
        on_thought: Callable[[Thought], None] = None,
        on_action: Callable[[ToolCall], None] = None,
        on_observation: Callable[[str], None] = None,
        enable_memory: bool = True,
        enable_vector_memory: bool = True,
        milvus_host: str = "localhost",
        milvus_port: str = "19530",
        enable_logging: bool = True
    ):
        self.llm = llm_client
        self.mcp = mcp_manager
        self.skill = skill_manager
        self.max_iterations = max_iterations

        # 回调函数
        self.on_thought = on_thought
        self.on_action = on_action
        self.on_observation = on_observation

        # 历史记录
        self.thoughts: List[Thought] = []
        self.messages: List[Message] = []

        # Memory 管理
        self.enable_memory = enable_memory
        self.memory = MemoryManager(llm_client=llm_client) if enable_memory else None

        # 向量记忆管理
        self.enable_vector_memory = enable_vector_memory
        self.vector_memory = None
        if enable_vector_memory:
            self.vector_memory = VectorMemoryManager(
                host=milvus_host,
                port=milvus_port
            )

        # 记录本轮工具调用信息
        self._current_tool_calls = []

        # 日志记录
        self.enable_logging = enable_logging
        self.logger = get_logger() if enable_logging else None

        # Token 统计
        self.session_token_usage = TokenUsage()  # 本次会话累计
        self.round_token_usage = TokenUsage()    # 当前轮次

    def _get_all_tools(self):
        """获取所有可用工具"""
        tools = []
        tools.extend(self.mcp.get_tools())
        tools.extend(self.skill.get_tools())
        return tools

    def reset_round_tokens(self):
        """重置当前轮次的 token 统计"""
        self.round_token_usage = TokenUsage()

    def get_token_stats(self) -> Dict[str, Any]:
        """获取 token 统计信息"""
        return {
            "round": self.round_token_usage.to_dict(),
            "session": self.session_token_usage.to_dict()
        }

    def format_token_stats(self) -> str:
        """格式化 token 统计为字符串"""
        round_stats = self.round_token_usage.to_dict()
        session_stats = self.session_token_usage.to_dict()

        lines = [
            "",
            "=" * 50,
            "Token 使用统计:",
            f"  本轮对话:",
            f"    输入: {round_stats['prompt_tokens']:,} tokens",
            f"    输出: {round_stats['completion_tokens']:,} tokens",
            f"    总计: {round_stats['total_tokens']:,} tokens",
            f"  本次会话累计:",
            f"    输入: {session_stats['prompt_tokens']:,} tokens",
            f"    输出: {session_stats['completion_tokens']:,} tokens",
            f"    总计: {session_stats['total_tokens']:,} tokens",
            "=" * 50
        ]
        return "\n".join(lines)

    async def run(self, user_input: str) -> str:
        """运行ReAct循环"""
        self.thoughts = []
        self._current_tool_calls = []  # 重置工具调用记录
        self.reset_round_tokens()  # 重置本轮 token 统计

        # 记录用户输入
        if self.logger:
            self.logger.log_separator("=")
            self.logger.log_user_input(user_input)
            self.logger.log_separator("-")

        # 连接向量数据库
        if self.vector_memory and not self.vector_memory._connected:
            self.vector_memory.connect()

        # 搜索相似记忆（只使用相似度 >= 阈值的结果）
        similar_memories = None
        if self.vector_memory:
            all_memories = self.vector_memory.search_similar(user_input, top_k=5)
            # 从环境变量读取相似度阈值，默认 0.7
            similarity_threshold = float(os.getenv("VECTOR_MEMORY_SIMILARITY_THRESHOLD", "0.7"))
            similar_memories = [
                mem for mem in all_memories
                if (1 / (1 + mem.get('distance', float('inf')))) >= similarity_threshold
            ]
            if similar_memories:
                print(f"\n[向量记忆] 找到 {len(similar_memories)} 条相关记录 (相似度 >= {similarity_threshold})")
                if self.logger:
                    self.logger.info(f"向量记忆找到 {len(similar_memories)} 条相关记录 (相似度 >= {similarity_threshold})")

        # 构建消息列表，融合两种记忆
        self.messages = self._build_messages_with_memory(user_input, similar_memories)

        tools = self._get_all_tools()

        for step in range(1, self.max_iterations + 1):
            print(f"\n{'='*50}")
            print(f"步骤 {step}/{self.max_iterations}")
            print(f"{'='*50}")

            if self.logger:
                self.logger.info(f"步骤 {step}/{self.max_iterations}")

            # 1. 思考
            print("\n[思考中...]")
            llm_response, token_usage = await self.llm.chat(self.messages, tools)

            # 累加 token 使用量
            self.round_token_usage.add(token_usage)
            self.session_token_usage.add(token_usage)

            # 记录 token 使用到日志
            if self.logger:
                self.logger.info(f"Token 使用: 输入={token_usage.prompt_tokens}, 输出={token_usage.completion_tokens}, 总计={token_usage.total_tokens}")

            # 创建思考记录
            thought = Thought(
                step=step,
                thought=llm_response
            )

            # 记录思考过程
            if self.logger:
                self.logger.log_thought(step, llm_response)

            # 检查是否是最终答案
            final_answer = self.llm.parse_final_answer(llm_response)

            # 调试：显示解析结果
            if self.logger:
                self.logger.debug(f"LLM响应长度: {len(llm_response)}")
                self.logger.debug(f"是否包含final标记: {'```final' in llm_response or '``` final' in llm_response}")
                self.logger.debug(f"解析到最终答案: {final_answer is not None}")

            if final_answer:
                thought.is_final = True
                thought.thought = final_answer
                self.thoughts.append(thought)

                print(f"\n[最终答案] {final_answer}")

                if self.on_thought:
                    self.on_thought(thought)

                # 记录最终答案
                if self.logger:
                    self.logger.log_final_answer(final_answer)
                    self.logger.log_separator("=")

                # 保存到 memory
                if self.memory:
                    self.memory.add_turn(user_input, final_answer)

                # 保存到向量记忆
                if self.vector_memory:
                    tool_info = self._format_tool_calls_for_storage()
                    self.vector_memory.add_memory(
                        query=user_input,
                        tool=tool_info,
                        content=final_answer
                    )

                # 显示 token 统计
                print(self.format_token_stats())

                return final_answer

            # 2. 解析行动
            action = self.llm.parse_action(llm_response)

            if action:
                thought.action = action
                print(f"\n[行动] 调用 {action.tool_name}")
                print(f"   参数: {json.dumps(action.parameters, ensure_ascii=False)}")

                # 记录工具调用
                if self.logger:
                    self.logger.log_action(step, action.tool_name, action.parameters)

                if self.on_action:
                    self.on_action(action)

                # 3. 执行工具
                print(f"\n[执行中...]")
                result = await self._execute_action(action)

                # 记录工具调用到列表
                self._current_tool_calls.append({
                    "tool_name": action.tool_name,
                    "parameters": action.parameters,
                    "result": result.data if result.success else f"错误: {result.error}",
                    "success": result.success
                })

                # 记录完整工具结果到日志（不截断）
                if self.logger:
                    self.logger.log_tool_result(step, action.tool_name, result.data if result.success else result.error, result.success)

                # 格式化观察结果
                if result.success:
                    if isinstance(result.data, (dict, list)):
                        observation = json.dumps(result.data, ensure_ascii=False, indent=2)
                    else:
                        observation = str(result.data)
                else:
                    observation = f"错误: {result.error}"

                thought.observation = observation

                status = "[OK]" if result.success else "[FAIL]"
                # 完整显示观察结果
                print(f"\n{status} 观察: {observation}")

                if self.on_observation:
                    self.on_observation(observation)
            else:
                # 如果没有解析到 action，但内容很长且没有工具调用标记，可能是直接回答
                if len(llm_response) > 100 and '```json' not in llm_response and 'action' not in llm_response.lower():
                    print(f"\n[直接回答] {llm_response[:200]}...")
                    thought.is_final = True
                    thought.thought = llm_response
                    self.thoughts.append(thought)

                    if self.logger:
                        self.logger.log_final_answer(llm_response)

                    # 保存到记忆
                    if self.memory:
                        self.memory.add_turn(user_input, llm_response)

                    # 保存到向量记忆
                    if self.vector_memory:
                        tool_info = self._format_tool_calls_for_storage()
                        self.vector_memory.add_memory(
                            query=user_input,
                            tool=tool_info,
                            content=llm_response
                        )

                    # 显示 token 统计
                    print(self.format_token_stats())

                    return llm_response
                else:
                    print(f"\n[思考内容] {llm_response[:200]}...")

            self.thoughts.append(thought)

            if self.on_thought:
                self.on_thought(thought)

            # 更新消息历史
            self._update_messages(thought)

        # 达到最大迭代次数
        fallback_answer = "达到最大迭代次数，未能完成任务。"
        if self.memory:
            self.memory.add_turn(user_input, fallback_answer)

        # 保存到向量记忆
        if self.vector_memory:
            tool_info = self._format_tool_calls_for_storage()
            self.vector_memory.add_memory(
                query=user_input,
                tool=tool_info,
                content=fallback_answer
            )

        # 显示 token 统计
        print(self.format_token_stats())

        return fallback_answer

    def _format_tool_calls_for_storage(self) -> str:
        """格式化工具调用信息用于存储"""
        if not self._current_tool_calls:
            return "无工具调用"

        parts = []
        for i, call in enumerate(self._current_tool_calls, 1):
            status = "成功" if call["success"] else "失败"
            parts.append(
                f"[{i}] 工具: {call['tool_name']}\n"
                f"    参数: {json.dumps(call['parameters'], ensure_ascii=False)}\n"
                f"    结果: {str(call['result'])[:200]}...\n"
                f"    状态: {status}"
            )

        return "\n".join(parts)

    def _build_messages_with_memory(self, user_input: str, similar_memories: list = None) -> List[Message]:
        """构建包含 memory 上下文的消息列表"""
        messages = []

        # 构建系统提示，融合两种记忆
        system_parts = []

        # 1. 添加文本记忆（滑动窗口记忆）
        if self.memory and (self.memory.memory_blocks or self.memory.current_turns):
            text_context = self.memory.get_context()
            system_parts.append(f"【近期对话历史】\n{text_context}")

        # 2. 添加向量记忆（相似语义记忆）
        if similar_memories:
            vector_parts = ["【相关历史经验】"]
            for i, mem in enumerate(similar_memories, 1):
                similarity = 1 / (1 + mem.get('distance', 0))
                vector_parts.append(
                    f"[相似度: {similarity:.2f}] 用户曾问: {mem.get('query', '')}\n"
                    f"  当时的回答: {mem.get('content', '')[:200]}..."
                )
            system_parts.append("\n".join(vector_parts))

        # 组合系统提示
        if system_parts:
            full_context = "\n\n".join(system_parts)
            messages.append(Message(
                role="system",
                content=f"以下是你的记忆上下文，包含近期对话和相关历史经验:\n\n{full_context}\n\n"
                        f"请基于以上上下文回答用户问题。如果历史经验中有相关信息，请优先参考。"
            ))

            # 添加当前对话窗口的历史（文本记忆）
            if self.memory and self.memory.current_turns:
                for turn in self.memory.current_turns:
                    messages.append(Message(role="user", content=turn.user_input))
                    messages.append(Message(role="assistant", content=turn.assistant_response))

        # 添加当前用户输入
        messages.append(Message(role="user", content=user_input))

        return messages

    async def _execute_action(self, action: ToolCall) -> ToolResult:
        """执行工具调用"""
        # 先检查MCP
        if action.tool_name in [t.name for t in self.mcp.get_tools()]:
            return await self.mcp.call_tool(action.tool_name, action.parameters)

        # 再检查Skill
        if action.tool_name in [t.name for t in self.skill.get_tools()]:
            return await self.skill.call_tool(action.tool_name, action.parameters)

        return ToolResult(
            success=False,
            data=None,
            error=f"未找到工具: {action.tool_name}"
        )

    def _update_messages(self, thought: Thought):
        """更新消息历史"""
        # 添加助手的思考
        content = thought.thought
        if thought.action:
            content += f"\n\n行动: 调用 {thought.action.tool_name}"

        self.messages.append(Message(role="assistant", content=content))

        # 添加观察结果（包含完整数据）
        if thought.observation:
            # 如果观察结果是结构化数据，提示 LLM 详细展示
            observation_content = thought.observation
            if len(observation_content) > 100 and ('[' in observation_content or '{' in observation_content):
                observation_content += "\n\n请以上述完整数据为基础，以表格形式展示详细信息。"

            self.messages.append(Message(
                role="user",
                content=f"观察结果: {observation_content}"
            ))

    def get_history(self) -> List[Thought]:
        """获取思考历史"""
        return self.thoughts.copy()

    def clear_history(self):
        """清除历史"""
        self.thoughts = []
        self.messages = []
        if self.memory:
            self.memory.clear()
        if self.vector_memory:
            self.vector_memory.clear()

    def get_memory_stats(self) -> dict:
        """获取 memory 统计信息"""
        stats = {}
        if self.memory:
            stats["text_memory"] = self.memory.get_stats()
        if self.vector_memory:
            stats["vector_memory"] = self.vector_memory.get_stats()
        return stats

    def search_vector_memory(self, query: str, top_k: int = 5) -> list:
        """搜索向量记忆"""
        if self.vector_memory:
            return self.vector_memory.search_similar(query, top_k)
        return []
