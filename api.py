"""
FastAPI 接口 - 智能体 API 服务
"""

import asyncio
import os
import re
import json
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent import Agent

# 全局智能体实例
agent: Optional[Agent] = None


# 请求/响应模型
class ChatRequest(BaseModel):
    """对话请求"""
    message: str = Field(..., description="用户输入消息")
    session_id: Optional[str] = Field(None, description="会话ID，用于区分不同会话")
    enable_memory: bool = Field(True, description="是否启用记忆功能")


class ThoughtStep(BaseModel):
    """思考步骤"""
    step: int = Field(..., description="步骤序号")
    thought: str = Field(..., description="思考内容")
    action: Optional[Dict[str, Any]] = Field(None, description="行动信息")
    observation: Optional[str] = Field(None, description="观察结果")
    is_final: bool = Field(False, description="是否为最终答案")


class ChatResponse(BaseModel):
    """对话响应"""
    success: bool = Field(..., description="是否成功")
    response: str = Field(..., description="智能体回复")
    session_id: Optional[str] = Field(None, description="会话ID")
    token_usage: Dict[str, Any] = Field(default_factory=dict, description="Token使用情况")
    execution_time: float = Field(0.0, description="执行时间（秒）")
    thoughts: List[ThoughtStep] = Field(default_factory=list, description="思考过程")


class ToolInfo(BaseModel):
    """工具信息"""
    name: str = Field(..., description="工具名称")
    type: str = Field(..., description="工具类型")
    description: str = Field(..., description="工具描述")


class ToolsResponse(BaseModel):
    """工具列表响应"""
    tools: List[ToolInfo] = Field(default_factory=list, description="可用工具列表")


class SkillInfo(BaseModel):
    """Skill信息"""
    name: str = Field(..., description="Skill名称")
    enabled: bool = Field(..., description="是否启用")
    loaded: bool = Field(..., description="是否已加载")
    source_path: str = Field(..., description="源路径")


class SkillsResponse(BaseModel):
    """Skill列表响应"""
    skills: List[SkillInfo] = Field(default_factory=list, description="Skill列表")


class SkillActionRequest(BaseModel):
    """Skill操作请求"""
    skill_name: str = Field(..., description="Skill名称")


class SkillActionResponse(BaseModel):
    """Skill操作响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="操作结果消息")


class MCPServerInfo(BaseModel):
    """MCP服务器信息"""
    name: str = Field(..., description="服务器名称")
    command: str = Field(..., description="启动命令")
    args: List[str] = Field(default_factory=list, description="启动参数")
    enabled: bool = Field(..., description="是否启用")
    running: bool = Field(..., description="是否运行中")


class MCPServersResponse(BaseModel):
    """MCP服务器列表响应"""
    servers: List[MCPServerInfo] = Field(default_factory=list, description="MCP服务器列表")


class MCPConfigRequest(BaseModel):
    """MCP配置请求"""
    name: str = Field(..., description="服务器名称")
    config: Dict[str, Any] = Field(..., description="服务器配置")


class MCPActionResponse(BaseModel):
    """MCP操作响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="操作结果消息")


class MemoryStats(BaseModel):
    """记忆统计"""
    text_memory: Optional[Dict[str, Any]] = Field(None, description="文本记忆统计")
    vector_memory: Optional[Dict[str, Any]] = Field(None, description="向量记忆统计")


class ChatHistoryItem(BaseModel):
    """对话历史项"""
    id: str = Field(..., description="会话ID")
    timestamp: str = Field(..., description="时间戳")
    user_message: str = Field(..., description="用户消息")
    assistant_response: str = Field(..., description="助手回复")
    token_usage: Dict[str, Any] = Field(default_factory=dict, description="Token使用情况")
    execution_time: float = Field(0.0, description="执行时间")


class ChatHistoryResponse(BaseModel):
    """对话历史响应"""
    success: bool = Field(..., description="是否成功")
    history: List[ChatHistoryItem] = Field(default_factory=list, description="历史对话列表")


class TokenStats(BaseModel):
    """Token统计"""
    round: Dict[str, int] = Field(default_factory=dict, description="本轮统计")
    session: Dict[str, int] = Field(default_factory=dict, description="会话累计统计")


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = Field(..., description="服务状态")
    timestamp: str = Field(..., description="当前时间")
    version: str = Field("1.0.0", description="API版本")


class FileInfo(BaseModel):
    """文件信息"""
    filename: str = Field(..., description="文件名")
    size: int = Field(..., description="文件大小（字节）")
    content_type: str = Field(..., description="文件类型")
    upload_time: str = Field(..., description="上传时间")
    path: str = Field(..., description="文件路径")


class FilesResponse(BaseModel):
    """文件列表响应"""
    success: bool = Field(..., description="是否成功")
    files: List[FileInfo] = Field(default_factory=list, description="文件列表")
    total: int = Field(0, description="文件总数")


class UploadResponse(BaseModel):
    """文件上传响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    file: Optional[FileInfo] = Field(None, description="单个文件信息")
    files: List[FileInfo] = Field(default_factory=list, description="多个文件信息列表")
    total: int = Field(0, description="上传文件总数")


class FileActionResponse(BaseModel):
    """文件操作响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="操作结果消息")


# 文件上传目录
UPLOAD_DIR = Path("uploads")


# 生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global agent

    # 启动时初始化智能体
    print("=" * 60)
    print("正在初始化智能体...")
    print("=" * 60)

    # 确保上传目录存在
    UPLOAD_DIR.mkdir(exist_ok=True)
    print(f"文件上传目录: {UPLOAD_DIR.absolute()}")

    agent = Agent(
        enable_memory=True,
        enable_vector_memory=True,
        milvus_host=os.getenv("MILVUS_HOST", "localhost"),
        milvus_port=os.getenv("MILVUS_PORT", "19530")
    )

    try:
        await agent.initialize()
        print("\n智能体初始化完成！")
        print(f"可用工具数量: {len(agent.get_available_tools())}")
    except Exception as e:
        print(f"\n智能体初始化失败: {e}")
        raise

    yield

    # 关闭时清理资源
    print("\n正在关闭智能体...")
    if agent:
        try:
            await agent.cleanup_async()
        except:
            agent.cleanup()
    print("智能体已关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title="智能体 API",
    description="基于 ReAct 的智能体 API 服务，支持 MCP 工具和 Skill",
    version="1.0.0",
    lifespan=lifespan
)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# API 路由
@app.get("/", response_model=HealthResponse)
async def root():
    """根路径 - 健康检查"""
    return HealthResponse(
        status="running",
        timestamp=datetime.now().isoformat()
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    return HealthResponse(
        status="healthy" if agent and agent._initialized else "not_ready",
        timestamp=datetime.now().isoformat()
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    与智能体对话

    - **message**: 用户输入的消息
    - **session_id**: 可选的会话ID
    - **enable_memory**: 是否启用记忆功能
    """
    if not agent or not agent._initialized:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    import time
    start_time = time.time()

    try:
        # 运行对话
        response = await agent.run(request.message)

        # 获取 token 统计
        token_usage = {}
        thoughts = []
        print(f"[API] agent.react = {agent.react}")
        if agent.react:
            token_stats = agent.react.get_token_stats()
            token_usage = {
                "round": token_stats.get("round", {}),
                "session": token_stats.get("session", {})
            }
            # 获取思考过程
            history = agent.react.get_history()
            print(f"[API] 获取到 {len(history)} 条思考记录")
            for i, t in enumerate(history):
                print(f"  步骤 {i+1}: thought={t.thought[:50]}..., is_final={t.is_final}")
            thoughts = [
                ThoughtStep(
                    step=i+1,
                    thought=t.thought,
                    action={
                        "tool_name": t.action.tool_name,
                        "parameters": t.action.parameters
                    } if t.action else None,
                    observation=t.observation,
                    is_final=t.is_final
                )
                for i, t in enumerate(history)
            ]
        else:
            print("[API] agent.react 为 None，无法获取思考记录")

        execution_time = time.time() - start_time

        return ChatResponse(
            success=True,
            response=response,
            session_id=request.session_id,
            token_usage=token_usage,
            execution_time=round(execution_time, 2),
            thoughts=thoughts
        )

    except Exception as e:
        execution_time = time.time() - start_time
        return ChatResponse(
            success=False,
            response=f"错误: {str(e)}",
            session_id=request.session_id,
            execution_time=round(execution_time, 2)
        )


@app.get("/tools", response_model=ToolsResponse)
async def get_tools():
    """获取可用工具列表"""
    if not agent or not agent._initialized:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    tools = agent.get_available_tools()
    tool_list = [
        ToolInfo(
            name=tool["name"],
            type=tool["type"],
            description=tool.get("description", "")
        )
        for tool in tools
    ]

    return ToolsResponse(tools=tool_list)


@app.get("/skills", response_model=SkillsResponse)
async def get_skills():
    """获取所有 Skill 列表"""
    if not agent or not agent.skill:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    skills = agent.skill.list_skills()
    skill_list = [
        SkillInfo(
            name=skill["name"],
            enabled=skill["enabled"],
            loaded=skill["loaded"],
            source_path=skill.get("source_path", "")
        )
        for skill in skills
    ]

    return SkillsResponse(skills=skill_list)


@app.post("/skills/{skill_name}/enable", response_model=SkillActionResponse)
async def enable_skill(skill_name: str):
    """启用指定 Skill"""
    if not agent or not agent.skill:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    success, message = agent.skill.enable_skill(skill_name)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return SkillActionResponse(success=True, message=message)


@app.post("/skills/{skill_name}/disable", response_model=SkillActionResponse)
async def disable_skill(skill_name: str):
    """停用指定 Skill"""
    if not agent or not agent.skill:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    success, message = agent.skill.disable_skill(skill_name)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return SkillActionResponse(success=True, message=message)


@app.post("/skills/add", response_model=SkillActionResponse)
async def add_skill(source_dir: str, skill_name: Optional[str] = None):
    """
    添加新的 Skill

    - **source_dir**: 源 Skill 目录路径
    - **skill_name**: 可选的 Skill 名称
    """
    if not agent or not agent.skill:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    success, message = agent.skill.add_skill(source_dir, skill_name)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return SkillActionResponse(success=True, message=message)


@app.delete("/skills/{skill_name}", response_model=SkillActionResponse)
async def remove_skill(skill_name: str):
    """删除指定 Skill"""
    if not agent or not agent.skill:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    success, message = agent.skill.remove_skill(skill_name)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return SkillActionResponse(success=True, message=message)


# ========== MCP 管理接口 ==========

@app.get("/mcp/servers", response_model=MCPServersResponse)
async def get_mcp_servers():
    """获取所有 MCP 服务器列表"""
    if not agent or not agent.mcp:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    servers = agent.mcp.list_mcp_servers()
    server_list = [
        MCPServerInfo(
            name=server["name"],
            command=server["command"],
            args=server.get("args", []),
            enabled=server["enabled"],
            running=server["running"]
        )
        for server in servers
    ]

    return MCPServersResponse(servers=server_list)


@app.post("/mcp/servers", response_model=MCPActionResponse)
async def add_mcp_server(request: MCPConfigRequest):
    """
    添加 MCP 服务器配置

    - **name**: 服务器名称
    - **config**: 服务器配置，包含 command 和 args
    """
    if not agent or not agent.mcp:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    success, message = agent.mcp.add_mcp_server(request.name, request.config)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return MCPActionResponse(success=True, message=message)


@app.delete("/mcp/servers/{server_name}", response_model=MCPActionResponse)
async def remove_mcp_server(server_name: str):
    """删除 MCP 服务器配置"""
    if not agent or not agent.mcp:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    success, message = agent.mcp.remove_mcp_server(server_name)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return MCPActionResponse(success=True, message=message)


@app.post("/mcp/servers/{server_name}/enable", response_model=MCPActionResponse)
async def enable_mcp_server(server_name: str):
    """启用 MCP 服务器"""
    if not agent or not agent.mcp:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    success, message = agent.mcp.enable_mcp_server(server_name)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return MCPActionResponse(success=True, message=message)


@app.post("/mcp/servers/{server_name}/disable", response_model=MCPActionResponse)
async def disable_mcp_server(server_name: str):
    """停用 MCP 服务器"""
    if not agent or not agent.mcp:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    success, message = agent.mcp.disable_mcp_server(server_name)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return MCPActionResponse(success=True, message=message)


@app.post("/mcp/servers/{server_name}/start", response_model=MCPActionResponse)
async def start_mcp_server(server_name: str):
    """启动 MCP 服务器"""
    if not agent or not agent.mcp:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    success, message = await agent.mcp.start_mcp_server(server_name)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return MCPActionResponse(success=True, message=message)


@app.post("/mcp/servers/{server_name}/stop", response_model=MCPActionResponse)
async def stop_mcp_server(server_name: str):
    """停止 MCP 服务器"""
    if not agent or not agent.mcp:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    success, message = await agent.mcp.stop_mcp_server(server_name)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return MCPActionResponse(success=True, message=message)


@app.get("/mcp/tools/disabled", response_model=List[str])
async def get_disabled_tools():
    """获取被禁用的工具列表"""
    if not agent or not agent.mcp:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    return agent.mcp.list_disabled_tools()


@app.get("/mcp/tools/all", response_model=ToolsResponse)
async def get_all_mcp_tools():
    """获取所有MCP工具（包括已禁用的）"""
    if not agent or not agent.mcp:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    # 获取所有工具（包括已禁用的）
    all_tools = []
    disabled_tools = agent.mcp.list_disabled_tools()

    # 从 mcp.tools 字典中获取所有工具
    for tool_name, (mcp_name, tool) in agent.mcp.tools.items():
        all_tools.append({
            "name": tool_name,
            "type": "MCP",
            "description": tool.description if hasattr(tool, 'description') else ""
        })

    # 添加被禁用但不在 tools 字典中的工具（可能属于已停止的服务器）
    for tool_name in disabled_tools:
        if tool_name not in agent.mcp.tools:
            all_tools.append({
                "name": tool_name,
                "type": "MCP",
                "description": "(已禁用 - 所属服务器未运行)"
            })

    tool_list = [ToolInfo(**tool) for tool in all_tools]
    return ToolsResponse(tools=tool_list)


@app.post("/mcp/tools/{tool_name}/disable", response_model=MCPActionResponse)
async def disable_tool(tool_name: str):
    """
    禁用单个工具

    - **tool_name**: 工具名称
    """
    if not agent or not agent.mcp:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    success, message = agent.mcp.disable_tool(tool_name)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return MCPActionResponse(success=True, message=message)


@app.post("/mcp/tools/{tool_name}/enable", response_model=MCPActionResponse)
async def enable_tool(tool_name: str):
    """
    启用单个工具

    - **tool_name**: 工具名称
    """
    if not agent or not agent.mcp:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    success, message = agent.mcp.enable_tool(tool_name)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return MCPActionResponse(success=True, message=message)


@app.get("/memory/stats", response_model=MemoryStats)
async def get_memory_stats():
    """获取记忆统计信息"""
    if not agent or not agent.react:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    stats = agent.get_memory_stats()

    return MemoryStats(
        text_memory=stats.get("text_memory"),
        vector_memory=stats.get("vector_memory")
    )


@app.post("/memory/clear")
async def clear_memory():
    """清除记忆"""
    if not agent or not agent.react:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    agent.clear_history()

    return {"success": True, "message": "记忆已清除"}


@app.get("/tokens", response_model=TokenStats)
async def get_token_stats():
    """获取 Token 使用统计"""
    if not agent or not agent.react:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    token_stats = agent.react.get_token_stats()

    return TokenStats(
        round=token_stats.get("round", {}),
        session=token_stats.get("session", {})
    )


@app.post("/memory/search")
async def search_memory(query: str, top_k: int = 5):
    """
    搜索向量记忆

    - **query**: 搜索查询
    - **top_k**: 返回结果数量
    """
    if not agent or not agent.react:
        raise HTTPException(status_code=503, detail="智能体未初始化")

    results = agent.react.search_vector_memory(query, top_k=top_k)

    return {
        "success": True,
        "query": query,
        "results": results
    }


if __name__ == "__main__":
    import uvicorn

    # 从环境变量读取配置
def parse_log_files() -> List[ChatHistoryItem]:
    """解析日志文件，提取历史对话"""
    history = []
    base_dir = Path(__file__).parent
    log_dir = base_dir / "log"

    if not log_dir.exists():
        print(f"[API] 日志目录不存在: {log_dir}")
        return history

    # 获取所有 session 日志文件
    log_files = sorted(log_dir.glob("session_*.log"), reverse=True)

    for log_file in log_files[:50]:  # 只取最近50个
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 提取会话ID
            session_id = log_file.stem

            # 解析用户输入和最终答案
            # 查找用户输入模式
            user_inputs = re.findall(
                r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\].*?用户输入: (.+?)(?:\n|$)',
                content
            )

            # 查找最终答案模式
            final_answers = re.findall(
                r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\].*?最终答案: (.+?)(?:\n={80}|\Z)',
                content,
                re.DOTALL
            )

            # 匹配用户输入和回复
            for i, (timestamp, user_msg) in enumerate(user_inputs):
                if i < len(final_answers):
                    _, response = final_answers[i]
                    # 清理响应内容
                    response = response.strip()

                    # 提取token使用情况
                    token_match = re.search(
                        r'Token 使用: 输入=(\d+), 输出=(\d+), 总计=(\d+)',
                        content
                    )
                    token_usage = {}
                    if token_match:
                        token_usage = {
                            "prompt_tokens": int(token_match.group(1)),
                            "completion_tokens": int(token_match.group(2)),
                            "total_tokens": int(token_match.group(3))
                        }

                    history.append(ChatHistoryItem(
                        id=f"{session_id}_{i}",
                        timestamp=timestamp,
                        user_message=user_msg.strip(),
                        assistant_response=response,
                        token_usage=token_usage,
                        execution_time=0.0
                    ))

        except Exception as e:
            print(f"解析日志文件失败 {log_file}: {e}")
            continue

    # 按时间倒序排列
    history.sort(key=lambda x: x.timestamp, reverse=True)
    return history[:100]  # 最多返回100条


@app.get("/history", response_model=ChatHistoryResponse)
async def get_chat_history():
    """获取历史对话列表"""
    try:
        history = parse_log_files()
        return ChatHistoryResponse(success=True, history=history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取历史对话失败: {str(e)}")


@app.get("/history/{session_id}")
async def get_chat_detail(session_id: str):
    """获取特定会话的详细信息"""
    try:
        log_file = Path(f"log/{session_id}.log")
        if not log_file.exists():
            raise HTTPException(status_code=404, detail="会话不存在")

        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()

        return {
            "success": True,
            "session_id": session_id,
            "content": content
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取会话详情失败: {str(e)}")


@app.delete("/history/{session_id}")
async def delete_chat_history(session_id: str):
    """删除特定会话的历史记录"""
    try:
        print(f"[API] 删除会话请求: {session_id}")

        # 使用绝对路径
        base_dir = Path(__file__).parent
        log_dir = base_dir / "log"

        # 构建文件路径
        log_file = log_dir / f"{session_id}.log"
        print(f"[API] 尝试删除文件: {log_file}")
        print(f"[API] 文件是否存在: {log_file.exists()}")

        if log_file.exists():
            log_file.unlink()
            print(f"[API] 文件已删除: {log_file}")
        else:
            print(f"[API] 文件不存在: {log_file}")

        # 同时删除对应的工具结果文件
        tool_file = log_dir / f"tool_results_{session_id.replace('session_', '')}.jsonl"
        print(f"[API] 尝试删除工具结果文件: {tool_file}")

        if tool_file.exists():
            tool_file.unlink()
            print(f"[API] 工具结果文件已删除: {tool_file}")
        else:
            print(f"[API] 工具结果文件不存在: {tool_file}")

        return {"success": True, "message": "会话已删除"}
    except Exception as e:
        print(f"[API] 删除会话失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除会话失败: {str(e)}")


# ========== 文件管理接口 ==========

def sanitize_filename(filename: str) -> str:
    """清理文件名，移除不安全字符，保留中文"""
    import re
    # 保留中文、英文、数字、下划线、点号和连字符
    # 替换其他特殊字符为下划线
    safe_name = re.sub(r'[^\w\u4e00-\u9fa5.\-]', '_', filename)
    # 移除连续的下划线
    safe_name = re.sub(r'_+', '_', safe_name)
    # 限制长度
    if len(safe_name) > 200:
        name, ext = os.path.splitext(safe_name)
        safe_name = name[:200 - len(ext)] + ext
    return safe_name


@app.post("/upload", response_model=UploadResponse)
async def upload_files(files: List[UploadFile] = File(...)):
    """
    上传文件（支持多文件）

    - **files**: 要上传的文件列表
    """
    try:
        uploaded_files = []
        max_size = 100 * 1024 * 1024  # 100MB 单文件限制
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for idx, file in enumerate(files):
            # 读取文件内容
            file_content = await file.read()

            # 检查文件大小
            if len(file_content) > max_size:
                raise HTTPException(
                    status_code=413,
                    detail=f"文件 '{file.filename}' 大小超过100MB限制"
                )

            # 清理文件名（支持中文）
            safe_name = sanitize_filename(file.filename)
            safe_filename = f"{timestamp}_{idx}_{safe_name}"
            file_path = UPLOAD_DIR / safe_filename

            # 保存文件
            with open(file_path, "wb") as f:
                f.write(file_content)

            # 获取文件信息
            file_stat = file_path.stat()
            file_info = FileInfo(
                filename=safe_filename,
                size=file_stat.st_size,
                content_type=file.content_type or "application/octet-stream",
                upload_time=datetime.now().isoformat(),
                path=str(file_path.absolute())
            )
            uploaded_files.append(file_info)

        return UploadResponse(
            success=True,
            message=f"成功上传 {len(uploaded_files)} 个文件",
            files=uploaded_files,
            total=len(uploaded_files)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")


@app.post("/upload/folder", response_model=UploadResponse)
async def upload_folder(files: List[UploadFile] = File(...), folder_name: str = ""):
    """
    上传文件夹（支持多文件，保持目录结构）

    - **files**: 文件夹内的文件列表（包含相对路径）
    - **folder_name**: 文件夹名称（可选）
    """
    try:
        uploaded_files = []
        max_size = 100 * 1024 * 1024  # 100MB 单文件限制
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 创建文件夹目录
        if folder_name:
            folder_dir = UPLOAD_DIR / f"{timestamp}_{folder_name}"
        else:
            folder_dir = UPLOAD_DIR / f"{timestamp}_folder"
        folder_dir.mkdir(exist_ok=True)

        for file in files:
            # 读取文件内容
            file_content = await file.read()

            # 检查文件大小
            if len(file_content) > max_size:
                raise HTTPException(
                    status_code=413,
                    detail=f"文件 '{file.filename}' 大小超过100MB限制"
                )

            # 处理文件路径（保持目录结构）
            # file.filename 可能包含相对路径，如 "folder/subfolder/file.txt"
            # 清理文件名（支持中文）
            safe_name = sanitize_filename(Path(file.filename).name)
            relative_path = Path(file.filename).parent / safe_name
            safe_path = folder_dir / relative_path

            # 安全检查：确保文件在目标目录内
            if not safe_path.resolve().is_relative_to(folder_dir.resolve()):
                raise HTTPException(status_code=403, detail=f"非法的文件路径: {file.filename}")

            # 确保子目录存在
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            # 保存文件
            with open(safe_path, "wb") as f:
                f.write(file_content)

            # 获取文件信息
            file_stat = safe_path.stat()
            file_info = FileInfo(
                filename=str(safe_path.relative_to(UPLOAD_DIR)),
                size=file_stat.st_size,
                content_type=file.content_type or "application/octet-stream",
                upload_time=datetime.now().isoformat(),
                path=str(safe_path.absolute())
            )
            uploaded_files.append(file_info)

        return UploadResponse(
            success=True,
            message=f"成功上传文件夹，包含 {len(uploaded_files)} 个文件",
            files=uploaded_files,
            total=len(uploaded_files)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件夹上传失败: {str(e)}")


@app.get("/files", response_model=FilesResponse)
async def list_files():
    """获取已上传文件列表"""
    try:
        files = []
        for file_path in UPLOAD_DIR.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                files.append(FileInfo(
                    filename=file_path.name,
                    size=stat.st_size,
                    content_type="application/octet-stream",
                    upload_time=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    path=str(file_path.absolute())
                ))

        # 按上传时间倒序排列
        files.sort(key=lambda x: x.upload_time, reverse=True)

        return FilesResponse(
            success=True,
            files=files,
            total=len(files)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文件列表失败: {str(e)}")


@app.get("/files/{filename}")
async def download_file(filename: str):
    """
    下载文件

    - **filename**: 文件名
    """
    try:
        file_path = UPLOAD_DIR / filename

        # 安全检查：确保文件在 uploads 目录内
        if not file_path.resolve().is_relative_to(UPLOAD_DIR.resolve()):
            raise HTTPException(status_code=403, detail="非法的文件路径")

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        return FileResponse(
            path=file_path,
            filename=filename,
            media_type="application/octet-stream"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件下载失败: {str(e)}")


@app.delete("/files/{filename}", response_model=FileActionResponse)
async def delete_file(filename: str):
    """
    删除文件

    - **filename**: 文件名
    """
    try:
        file_path = UPLOAD_DIR / filename

        # 安全检查：确保文件在 uploads 目录内
        if not file_path.resolve().is_relative_to(UPLOAD_DIR.resolve()):
            raise HTTPException(status_code=403, detail="非法的文件路径")

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        file_path.unlink()

        return FileActionResponse(
            success=True,
            message=f"文件已删除: {filename}"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件删除失败: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    reload = os.getenv("API_RELOAD", "false").lower() == "true"

    print(f"""
╔══════════════════════════════════════════════════════════╗
║              智能体 API 服务                             ║
╠══════════════════════════════════════════════════════════╣
║  文档地址: http://{host}:{port}/docs                     ║
║  API地址: http://{host}:{port}                           ║
╚══════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "api:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )
