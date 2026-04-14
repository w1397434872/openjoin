"""
MCP管理器 - 管理MCP工具的配置和调用
实现完整的 MCP 协议支持
"""

import json
import asyncio
import subprocess
import os
from typing import Any, Dict, List, Optional, Tuple
from .custom_types import Tool, ToolType, ToolResult


class MCPConnection:
    """MCP 连接封装"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.tools: List[Dict[str, Any]] = []
        self._initialized = False
        self._request_id = 0
    
    def _get_next_id(self) -> int:
        """获取下一个请求ID"""
        self._request_id += 1
        return self._request_id
    
    async def initialize(self) -> Tuple[bool, str]:
        """初始化 MCP 连接"""
        try:
            command = self.config['command']
            args = self.config.get('args', [])
            env = self.config.get('env', {})
            
            # 合并环境变量
            full_env = {**dict(os.environ), **env} if env else None
            
            # 启动进程
            self.process = await asyncio.create_subprocess_exec(
                command, *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=full_env
            )
            
            # 等待进程启动
            await asyncio.sleep(0.5)
            
            # 检查进程是否还在运行
            if self.process.returncode is not None:
                stderr = await self.process.stderr.read()
                error_msg = stderr.decode() if stderr else "进程启动后立即退出"
                return False, f"进程启动失败: {error_msg[:200]}"
            
            # 发送 initialize 请求
            init_request = {
                "jsonrpc": "2.0",
                "id": self._get_next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "python-agent",
                        "version": "1.0.0"
                    }
                }
            }
            
            response = await self._send_request(init_request)
            
            if 'error' in response:
                return False, f"初始化失败: {response['error']}"
            
            # 发送 initialized 通知
            initialized_notification = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            await self._send_notification(initialized_notification)
            
            self._initialized = True
            
            # 获取工具列表
            await self._discover_tools()
            
            return True, f"已发现 {len(self.tools)} 个工具"
            
        except Exception as e:
            return False, f"初始化异常: {str(e)}"
    
    async def _drain_stderr(self):
        """后台任务：持续读取 stderr 防止缓冲区满"""
        try:
            while self.process and self.process.returncode is None:
                try:
                    line = await asyncio.wait_for(
                        self.process.stderr.readline(),
                        timeout=1.0
                    )
                    if line:
                        decoded = line.decode().strip()
                        if decoded:
                            print(f"    [MCP {self.name}] stderr: {decoded[:200]}")
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break
        except Exception:
            pass

    async def _send_request(self, request: Dict) -> Dict:
        """发送请求并等待响应，跳过非JSON的日志输出"""
        if not self.process or self.process.stdin.is_closing():
            return {"error": "进程未运行"}
        
        # 启动后台任务读取 stderr
        stderr_task = asyncio.create_task(self._drain_stderr())
        
        try:
            request_json = json.dumps(request) + '\n'
            self.process.stdin.write(request_json.encode())
            await self.process.stdin.drain()
            
            # 读取响应，跳过非JSON行
            max_retries = 10
            for attempt in range(max_retries):
                try:
                    line = await asyncio.wait_for(
                        self.process.stdout.readline(),
                        timeout=60.0
                    )
                    decoded_line = line.decode().strip()
                    
                    # 跳过空行
                    if not decoded_line:
                        continue
                    
                    # 调试：打印原始响应
                    print(f"    [MCP {self.name}] 原始响应: {decoded_line[:200]}")
                    
                    # 尝试解析JSON
                    try:
                        return json.loads(decoded_line)
                    except json.JSONDecodeError:
                        # 不是JSON，可能是日志输出，继续读取下一行
                        print(f"    [MCP {self.name}] 跳过非JSON输出")
                        continue
                        
                except asyncio.TimeoutError:
                    return {"error": "请求超时"}
            
            # 超过最大重试次数
            return {"error": f"未收到有效JSON响应（已尝试{max_retries}次）"}
        finally:
            # 取消 stderr 读取任务
            stderr_task.cancel()
            try:
                await stderr_task
            except asyncio.CancelledError:
                pass
    
    async def _send_notification(self, notification: Dict) -> None:
        """发送通知（不需要响应）"""
        if self.process and not self.process.stdin.is_closing():
            notification_json = json.dumps(notification) + '\n'
            self.process.stdin.write(notification_json.encode())
            await self.process.stdin.drain()
    
    async def _discover_tools(self) -> None:
        """发现可用工具"""
        request = {
            "jsonrpc": "2.0",
            "id": self._get_next_id(),
            "method": "tools/list"
        }
        
        response = await self._send_request(request)
        
        if 'result' in response and 'tools' in response['result']:
            self.tools = response['result']['tools']
    
    async def call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        """调用工具"""
        if not self._initialized:
            return ToolResult(success=False, data=None, error="MCP 未初始化")
        
        request = {
            "jsonrpc": "2.0",
            "id": self._get_next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": parameters
            }
        }
        
        response = await self._send_request(request)
        
        # 确保 response 是字典
        if not isinstance(response, dict):
            return ToolResult(
                success=False,
                data=None,
                error=f"无效的响应格式: {type(response).__name__}"
            )
        
        if 'error' in response:
            error_msg = response['error']
            if isinstance(error_msg, dict):
                error_msg = error_msg.get('message', str(error_msg))
            else:
                error_msg = str(error_msg)
            return ToolResult(
                success=False,
                data=None,
                error=error_msg
            )
        
        # 解析 MCP 工具返回的结果
        result = response.get('result', {})
        
        # MCP 协议中，工具结果通常在 content 字段中
        if 'content' in result:
            content = result['content']
            # content 是一个列表，包含 text 类型的内容
            if isinstance(content, list) and len(content) > 0:
                # 提取所有 text 类型的内容
                texts = []
                for item in content:
                    if isinstance(item, dict) and item.get('type') == 'text':
                        text = item.get('text', '')
                        # 尝试解析嵌套的 JSON 字符串
                        try:
                            parsed = json.loads(text)
                            texts.append(parsed)
                        except (json.JSONDecodeError, TypeError):
                            texts.append(text)
                
                # 如果只有一个结果，直接返回；否则返回列表
                if len(texts) == 1:
                    return ToolResult(success=True, data=texts[0])
                else:
                    return ToolResult(success=True, data=texts)
            else:
                return ToolResult(success=True, data=content)
        else:
            return ToolResult(success=True, data=result)
    
    async def cleanup_async(self):
        """异步清理资源"""
        if self.process:
            try:
                # 关闭 stdin 管道
                if self.process.stdin:
                    self.process.stdin.close()
                    try:
                        await self.process.stdin.wait_closed()
                    except:
                        pass
                
                # 关闭 stdout 和 stderr 管道
                if self.process.stdout:
                    self.process.stdout._transport.close()
                if self.process.stderr:
                    self.process.stderr._transport.close()
                
                # 终止进程
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=2)
                except asyncio.TimeoutError:
                    self.process.kill()
                    await self.process.wait()
            except Exception as e:
                print(f"清理进程时出错: {e}")
            finally:
                self.process = None
        self._initialized = False
    
    def cleanup(self):
        """同步清理资源（用于析构时）"""
        if self.process:
            try:
                self.process._transport.close()
            except:
                pass
            try:
                self.process.terminate()
            except:
                pass
            self.process = None
        self._initialized = False


class MCPManager:
    """MCP管理器"""
    
    def __init__(self, config_path: str = "config/mcp_config.json"):
        self.config_path = config_path
        self.connections: Dict[str, MCPConnection] = {}
        self.tools: Dict[str, Tuple[str, Tool]] = {}  # tool_name -> (mcp_name, Tool)
        self.disabled_tools: set = set()  # 被禁用的工具名称集合
        
    async def load_config(self) -> None:
        """加载MCP配置并初始化连接"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 支持两种配置格式:
            # 1. 旧格式: { "mcps": [ { "name": "xxx", "enabled": true, ... } ] }
            # 2. 新格式: { "mcpServers": { "xxx": { "command": "...", ... } } }

            mcp_servers = []

            # 检查新格式 mcpServers
            if 'mcpServers' in config:
                for name, server_config in config['mcpServers'].items():
                    # 新格式默认启用，除非明确指定 disabled: true
                    if not server_config.get('disabled', False):
                        mcp_config = dict(server_config)
                        mcp_config['name'] = name
                        mcp_config['enabled'] = True
                        mcp_servers.append(mcp_config)

            # 检查旧格式 mcps
            elif 'mcps' in config:
                for mcp_config in config.get('mcps', []):
                    if mcp_config.get('enabled', False):
                        mcp_servers.append(mcp_config)

            # 初始化连接
            for mcp_config in mcp_servers:
                name = mcp_config['name']
                print(f"  正在连接 MCP: {name}...")

                connection = MCPConnection(name, mcp_config)
                success, message = await connection.initialize()

                if success:
                    self.connections[name] = connection
                    print(f"  [OK] {name}: {message}")

                    # 注册工具
                    for tool_info in connection.tools:
                        tool_name = tool_info.get('name', 'unknown')
                        tool = Tool(
                            name=tool_name,
                            description=tool_info.get('description', f'MCP工具: {tool_name}'),
                            type=ToolType.MCP,
                            parameters=tool_info.get('inputSchema', {}),
                            config={"mcp_name": name}
                        )
                        self.tools[tool_name] = (name, tool)
                else:
                    print(f"  [FAIL] {name}: {message}")

            print(f"\n已加载 {len(self.connections)} 个MCP服务器，共 {len(self.tools)} 个工具")

        except Exception as e:
            print(f"加载MCP配置失败: {e}")
    
    def get_tools(self) -> List[Tool]:
        """获取所有可用的MCP工具（只返回正在运行的服务器的工具，且未被单独禁用）"""
        available_tools = []
        for tool_name, (mcp_name, tool) in self.tools.items():
            # 只返回正在运行的 MCP 服务器的工具
            if mcp_name in self.connections:
                # 且未被单独禁用
                if tool_name not in self.disabled_tools:
                    available_tools.append(tool)
        return available_tools
    
    def get_tool(self, name: str) -> Optional[Tool]:
        """获取指定工具"""
        if name in self.tools:
            return self.tools[name][1]
        return None
    
    async def call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        """调用MCP工具"""
        if tool_name not in self.tools:
            return ToolResult(success=False, data=None, error=f"MCP工具 '{tool_name}' 不存在")
        
        mcp_name, tool = self.tools[tool_name]
        connection = self.connections.get(mcp_name)
        
        if not connection:
            return ToolResult(
                success=False, 
                data=None, 
                error=f"MCP服务器 '{mcp_name}' 未运行或已被禁用，无法调用工具 '{tool_name}'"
            )
        
        return await connection.call_tool(tool_name, parameters)
    
    async def cleanup_async(self):
        """异步清理资源"""
        for connection in self.connections.values():
            await connection.cleanup_async()
        self.connections.clear()
        self.tools.clear()
    
    def cleanup(self):
        """同步清理资源"""
        for connection in self.connections.values():
            connection.cleanup()
        self.connections.clear()
        self.tools.clear()
    
    # ========== MCP 配置管理功能 ==========
    
    def _load_config_file(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {"mcpServers": {}}
        except Exception as e:
            print(f"读取配置文件失败: {e}")
            return {"mcpServers": {}}
    
    def _save_config_file(self, config: Dict[str, Any]) -> bool:
        """保存配置文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False
    
    def add_mcp_server(self, name: str, config: Dict[str, Any]) -> Tuple[bool, str]:
        """
        添加 MCP 服务器配置
        
        Args:
            name: MCP 服务器名称
            config: 配置字典，格式如 {"command": "...", "args": [...]}
        
        Returns:
            (success, message)
        """
        # 验证配置
        if 'command' not in config:
            return False, "配置必须包含 'command' 字段"
        
        # 加载现有配置
        file_config = self._load_config_file()
        
        # 确保 mcpServers 存在
        if 'mcpServers' not in file_config:
            file_config['mcpServers'] = {}
        
        # 检查是否已存在
        if name in file_config['mcpServers']:
            return False, f"MCP 服务器 '{name}' 已存在，请使用 update 命令更新"
        
        # 添加配置（默认启用）
        file_config['mcpServers'][name] = config
        
        # 保存配置
        if self._save_config_file(file_config):
            return True, f"MCP 服务器 '{name}' 已添加到配置"
        else:
            return False, "保存配置失败"
    
    def update_mcp_server(self, name: str, config: Dict[str, Any]) -> Tuple[bool, str]:
        """更新 MCP 服务器配置"""
        file_config = self._load_config_file()
        
        if 'mcpServers' not in file_config or name not in file_config['mcpServers']:
            return False, f"MCP 服务器 '{name}' 不存在"
        
        # 保留原有的 disabled 状态
        old_config = file_config['mcpServers'][name]
        if 'disabled' in old_config and 'disabled' not in config:
            config['disabled'] = old_config['disabled']
        
        file_config['mcpServers'][name] = config
        
        if self._save_config_file(file_config):
            return True, f"MCP 服务器 '{name}' 配置已更新"
        else:
            return False, "保存配置失败"
    
    def remove_mcp_server(self, name: str) -> Tuple[bool, str]:
        """删除 MCP 服务器配置"""
        file_config = self._load_config_file()
        
        if 'mcpServers' not in file_config or name not in file_config['mcpServers']:
            return False, f"MCP 服务器 '{name}' 不存在"
        
        # 如果正在运行，先停止
        if name in self.connections:
            asyncio.create_task(self.connections[name].cleanup_async())
            del self.connections[name]
            # 删除相关工具
            self.tools = {k: v for k, v in self.tools.items() if v[0] != name}
        
        del file_config['mcpServers'][name]
        
        if self._save_config_file(file_config):
            return True, f"MCP 服务器 '{name}' 已删除"
        else:
            return False, "保存配置失败"
    
    def enable_mcp_server(self, name: str) -> Tuple[bool, str]:
        """启用 MCP 服务器"""
        file_config = self._load_config_file()
        
        if 'mcpServers' not in file_config or name not in file_config['mcpServers']:
            return False, f"MCP 服务器 '{name}' 不存在"
        
        # 移除 disabled 标记
        if 'disabled' in file_config['mcpServers'][name]:
            del file_config['mcpServers'][name]['disabled']
        
        if self._save_config_file(file_config):
            return True, f"MCP 服务器 '{name}' 已启用，重启后生效"
        else:
            return False, "保存配置失败"
    
    def disable_mcp_server(self, name: str) -> Tuple[bool, str]:
        """停用 MCP 服务器"""
        file_config = self._load_config_file()
        
        if 'mcpServers' not in file_config or name not in file_config['mcpServers']:
            return False, f"MCP 服务器 '{name}' 不存在"
        
        # 添加 disabled 标记
        file_config['mcpServers'][name]['disabled'] = True
        
        # 如果正在运行，停止它
        if name in self.connections:
            asyncio.create_task(self.connections[name].cleanup_async())
            del self.connections[name]
        
        # 删除相关工具（无论是否在运行，都要清理）
        self.tools = {k: v for k, v in self.tools.items() if v[0] != name}
        
        if self._save_config_file(file_config):
            return True, f"MCP 服务器 '{name}' 已停用"
        else:
            return False, "保存配置失败"

    def disable_tool(self, tool_name: str) -> Tuple[bool, str]:
        """禁用单个工具"""
        if tool_name not in self.tools:
            return False, f"工具 '{tool_name}' 不存在"

        self.disabled_tools.add(tool_name)
        return True, f"工具 '{tool_name}' 已禁用"

    def enable_tool(self, tool_name: str) -> Tuple[bool, str]:
        """启用单个工具"""
        if tool_name not in self.disabled_tools:
            return False, f"工具 '{tool_name}' 未被禁用"

        self.disabled_tools.discard(tool_name)
        return True, f"工具 '{tool_name}' 已启用"

    def list_disabled_tools(self) -> List[str]:
        """列出所有被禁用的工具"""
        return list(self.disabled_tools)

    def list_mcp_servers(self) -> List[Dict[str, Any]]:
        """列出所有 MCP 服务器配置"""
        file_config = self._load_config_file()
        servers = []
        
        if 'mcpServers' in file_config:
            for name, config in file_config['mcpServers'].items():
                server_info = {
                    'name': name,
                    'command': config.get('command', ''),
                    'args': config.get('args', []),
                    'enabled': not config.get('disabled', False),
                    'running': name in self.connections
                }
                servers.append(server_info)
        
        return servers
    
    async def start_mcp_server(self, name: str) -> Tuple[bool, str]:
        """启动指定的 MCP 服务器"""
        file_config = self._load_config_file()
        
        if 'mcpServers' not in file_config or name not in file_config['mcpServers']:
            return False, f"MCP 服务器 '{name}' 不存在"
        
        server_config = file_config['mcpServers'][name]
        
        # 检查是否已禁用
        if server_config.get('disabled', False):
            return False, f"MCP 服务器 '{name}' 已被禁用，请先启用"
        
        # 检查是否已在运行
        if name in self.connections:
            return False, f"MCP 服务器 '{name}' 已在运行"
        
        # 启动连接
        mcp_config = dict(server_config)
        mcp_config['name'] = name
        mcp_config['enabled'] = True
        
        connection = MCPConnection(name, mcp_config)
        success, message = await connection.initialize()
        
        if success:
            self.connections[name] = connection
            # 注册工具
            for tool_info in connection.tools:
                tool_name = tool_info.get('name', 'unknown')
                tool = Tool(
                    name=tool_name,
                    description=tool_info.get('description', f'MCP工具: {tool_name}'),
                    type=ToolType.MCP,
                    parameters=tool_info.get('inputSchema', {}),
                    config={"mcp_name": name}
                )
                self.tools[tool_name] = (name, tool)
            return True, f"MCP 服务器 '{name}' 启动成功: {message}"
        else:
            return False, f"MCP 服务器 '{name}' 启动失败: {message}"
    
    async def stop_mcp_server(self, name: str) -> Tuple[bool, str]:
        """停止指定的 MCP 服务器"""
        if name not in self.connections:
            return False, f"MCP 服务器 '{name}' 未在运行"
        
        connection = self.connections[name]
        await connection.cleanup_async()
        del self.connections[name]
        
        # 删除相关工具
        self.tools = {k: v for k, v in self.tools.items() if v[0] != name}
        
        return True, f"MCP 服务器 '{name}' 已停止"
