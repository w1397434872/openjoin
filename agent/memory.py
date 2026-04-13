"""
Memory 管理模块 - 实现对话历史的智能压缩和摘要

功能特性:
- 最多保存15轮对话
- 总字数限制在1万字以内
- 当达到15轮或超过1万字时，前10轮生成100字摘要，与后5轮拼接
- 循环往复，保持上下文连贯性
"""

import os
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


@dataclass
class DialogueTurn:
    """单轮对话记录"""
    turn_id: int
    user_input: str
    assistant_response: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_text(self) -> str:
        """转换为文本格式"""
        return f"用户: {self.user_input}\n助手: {self.assistant_response}"
    
    def get_length(self) -> int:
        """获取字数"""
        return len(self.to_text())


@dataclass
class MemoryBlock:
    """记忆块 - 可以是完整对话或摘要"""
    block_id: int
    content: str
    is_summary: bool = False
    start_turn: int = 0
    end_turn: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    
    def get_length(self) -> int:
        """获取字数"""
        return len(self.content)


class MemoryManager:
    """
    Memory 管理器

    管理策略:
    - 维护一个当前窗口，保存最近对话
    - 当窗口满15轮或超过1万字时，触发压缩
    - 压缩时，前10轮生成100字摘要，后5轮保留完整内容
    - 摘要与保留的完整内容形成新的记忆块
    """

    # 从环境变量读取配置，使用默认值
    MAX_TURNS = int(os.getenv("MEMORY_MAX_TURNS", "15"))
    MAX_CHARS = int(os.getenv("MEMORY_MAX_CHARS", "10000"))
    SUMMARY_TURNS = int(os.getenv("MEMORY_SUMMARY_TURNS", "10"))
    KEEP_TURNS = int(os.getenv("MEMORY_KEEP_TURNS", "5"))
    SUMMARY_MAX_CHARS = int(os.getenv("MEMORY_SUMMARY_MAX_CHARS", "100"))

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

        # 当前活跃对话窗口
        self.current_turns: List[DialogueTurn] = []

        # 历史记忆块（已压缩的摘要+完整对话）
        self.memory_blocks: List[MemoryBlock] = []

        # 统计信息
        self.total_turns = 0
        self._block_counter = 0
    
    def add_turn(self, user_input: str, assistant_response: str) -> None:
        """
        添加一轮对话
        
        Args:
            user_input: 用户输入
            assistant_response: 助手回复
        """
        self.total_turns += 1
        turn = DialogueTurn(
            turn_id=self.total_turns,
            user_input=user_input,
            assistant_response=assistant_response
        )
        self.current_turns.append(turn)
        
        # 检查是否需要压缩
        self._check_and_compress()
    
    def _check_and_compress(self) -> None:
        """检查是否需要压缩，如需要则执行"""
        current_length = self._get_current_length()
        
        # 触发条件: 超过15轮 或 超过1万字
        if len(self.current_turns) >= self.MAX_TURNS or current_length >= self.MAX_CHARS:
            self._compress()
    
    def _get_current_length(self) -> int:
        """获取当前窗口的总字数"""
        return sum(turn.get_length() for turn in self.current_turns)
    
    def _compress(self) -> None:
        """
        执行压缩
        - 前10轮生成摘要
        - 后5轮保留完整内容
        """
        if len(self.current_turns) < self.SUMMARY_TURNS + self.KEEP_TURNS:
            # 对话轮数不足，不压缩
            return
        
        # 分离前10轮和后5轮
        turns_to_summarize = self.current_turns[:self.SUMMARY_TURNS]
        turns_to_keep = self.current_turns[self.SUMMARY_TURNS:]
        
        # 生成摘要
        summary = self._generate_summary(turns_to_summarize)
        
        # 构建保留内容的文本
        keep_content = "\n\n".join([turn.to_text() for turn in turns_to_keep])
        
        # 组合成新的记忆块
        self._block_counter += 1
        combined_content = f"【历史摘要】{summary}\n\n【近期对话】\n{keep_content}"
        
        memory_block = MemoryBlock(
            block_id=self._block_counter,
            content=combined_content,
            is_summary=True,
            start_turn=turns_to_summarize[0].turn_id,
            end_turn=turns_to_keep[-1].turn_id
        )
        
        self.memory_blocks.append(memory_block)
        
        # 清空当前窗口，将后5轮作为新的起点
        self.current_turns = turns_to_keep
    
    def _generate_summary(self, turns: List[DialogueTurn]) -> str:
        """
        生成对话摘要
        
        Args:
            turns: 需要摘要的对话轮次
            
        Returns:
            100字以内的摘要
        """
        # 构建对话文本
        dialogue_text = "\n".join([turn.to_text() for turn in turns])
        
        # 如果有LLM客户端，使用LLM生成摘要
        if self.llm_client:
            try:
                summary = self._generate_summary_with_llm(dialogue_text)
                if summary:
                    return summary[:self.SUMMARY_MAX_CHARS]
            except Exception as e:
                print(f"LLM摘要生成失败: {e}")
        
        # 降级方案：提取关键信息
        return self._generate_simple_summary(turns)
    
    def _generate_summary_with_llm(self, dialogue_text: str) -> Optional[str]:
        """使用LLM生成摘要"""
        prompt = f"""请对以下对话内容进行摘要，要求:
1. 控制在100字以内
2. 保留关键信息和上下文
3. 简明扼要

对话内容:
{dialogue_text}

摘要:"""
        
        try:
            # 这里假设llm_client有同步或异步的generate方法
            # 实际实现需要根据llm_client的接口调整
            if hasattr(self.llm_client, 'generate_sync'):
                return self.llm_client.generate_sync(prompt, max_tokens=150)
            return None
        except Exception:
            return None
    
    def _generate_simple_summary(self, turns: List[DialogueTurn]) -> str:
        """
        简单的摘要生成（降级方案）
        提取用户问题中的关键词
        """
        # 收集用户问题
        user_questions = [turn.user_input for turn in turns]
        
        # 简单的摘要逻辑：显示对话主题和轮数
        summary = f"共{len(turns)}轮对话，涉及主题: "
        
        # 提取前几个用户问题的开头部分
        topics = []
        for q in user_questions[:3]:
            # 取前20个字符作为主题
            topic = q[:20] + "..." if len(q) > 20 else q
            topics.append(topic)
        
        summary += "; ".join(topics)
        
        # 确保不超过100字
        if len(summary) > self.SUMMARY_MAX_CHARS:
            summary = summary[:self.SUMMARY_MAX_CHARS - 3] + "..."
        
        return summary
    
    def get_context(self) -> str:
        """
        获取完整的上下文内容
        
        Returns:
            包含历史摘要和当前对话的完整上下文
        """
        parts = []
        
        # 添加历史记忆块
        for block in self.memory_blocks:
            parts.append(block.content)
        
        # 添加当前对话窗口
        if self.current_turns:
            current_content = "\n\n".join([turn.to_text() for turn in self.current_turns])
            parts.append(f"【当前对话】\n{current_content}")
        
        return "\n\n".join(parts)
    
    def get_messages_for_llm(self) -> List[Dict[str, str]]:
        """
        获取格式化的消息列表，用于LLM对话
        
        Returns:
            格式化的消息列表
        """
        messages = []
        
        # 添加系统提示，说明有历史摘要
        if self.memory_blocks:
            context = self.get_context()
            messages.append({
                "role": "system",
                "content": f"以下是对话的历史上下文:\n\n{context}\n\n请基于以上上下文回答用户问题。"
            })
        
        # 添加当前对话（最后一条作为用户输入，不在这里添加）
        for turn in self.current_turns[:-1] if self.current_turns else []:
            messages.append({
                "role": "user",
                "content": turn.user_input
            })
            messages.append({
                "role": "assistant",
                "content": turn.assistant_response
            })
        
        return messages
    
    def clear(self) -> None:
        """清空所有记忆"""
        self.current_turns = []
        self.memory_blocks = []
        self.total_turns = 0
        self._block_counter = 0
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "total_turns": self.total_turns,
            "current_turns": len(self.current_turns),
            "memory_blocks": len(self.memory_blocks),
            "total_chars": self._get_total_chars()
        }
    
    def _get_total_chars(self) -> int:
        """获取总字数"""
        total = sum(block.get_length() for block in self.memory_blocks)
        total += self._get_current_length()
        return total
    
    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            "total_turns": self.total_turns,
            "block_counter": self._block_counter,
            "memory_blocks": [
                {
                    "block_id": b.block_id,
                    "content": b.content,
                    "is_summary": b.is_summary,
                    "start_turn": b.start_turn,
                    "end_turn": b.end_turn,
                    "timestamp": b.timestamp.isoformat()
                }
                for b in self.memory_blocks
            ],
            "current_turns": [
                {
                    "turn_id": t.turn_id,
                    "user_input": t.user_input,
                    "assistant_response": t.assistant_response,
                    "timestamp": t.timestamp.isoformat()
                }
                for t in self.current_turns
            ]
        }
    
    @classmethod
    def from_dict(cls, data: Dict, llm_client=None) -> "MemoryManager":
        """从字典反序列化"""
        manager = cls(llm_client=llm_client)
        manager.total_turns = data.get("total_turns", 0)
        manager._block_counter = data.get("block_counter", 0)
        
        # 恢复记忆块
        for block_data in data.get("memory_blocks", []):
            block = MemoryBlock(
                block_id=block_data["block_id"],
                content=block_data["content"],
                is_summary=block_data["is_summary"],
                start_turn=block_data["start_turn"],
                end_turn=block_data["end_turn"],
                timestamp=datetime.fromisoformat(block_data["timestamp"])
            )
            manager.memory_blocks.append(block)
        
        # 恢复当前对话
        for turn_data in data.get("current_turns", []):
            turn = DialogueTurn(
                turn_id=turn_data["turn_id"],
                user_input=turn_data["user_input"],
                assistant_response=turn_data["assistant_response"],
                timestamp=datetime.fromisoformat(turn_data["timestamp"])
            )
            manager.current_turns.append(turn)
        
        return manager
    
    def save_to_file(self, filepath: str) -> None:
        """保存到文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load_from_file(cls, filepath: str, llm_client=None) -> "MemoryManager":
        """从文件加载"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data, llm_client=llm_client)
