"""
智能体主程序入口
"""

import asyncio
import json
import sys
from agent import Agent


async def main():
    """主函数"""
    print("=" * 60)
    print("智能体系统启动")
    print("=" * 60)

    # 创建智能体（启用向量记忆）
    agent = Agent(
        enable_memory=True,
        enable_vector_memory=True,
        milvus_host="localhost",
        milvus_port="19530"
    )

    try:
        # 初始化（异步）
        await agent.initialize()

        # 显示可用工具
        print("\n可用工具:")
        tools = agent.get_available_tools()
        if tools:
            for tool in tools:
                print(f"  • [{tool['type']}] {tool['name']}: {tool['description']}")
        else:
            print("  (暂无可用工具，请配置MCP或Skill)")

        print("\n" + "=" * 60)
        print("输入 'quit' 或 'exit' 退出")
        print("输入 'mcp help' 查看MCP帮助")
        print("输入 'skill help' 查看Skill帮助")
        print("输入 'tools' 查看可用工具（仅显示MCP和Skill）")
        print("输入 'clear' 清除历史")
        print("输入 'memory' 查看记忆状态")
        print("输入 'search <查询>' 搜索向量记忆")
        print("输入 'logs' 查看日志文件路径")
        print("输入 'tokens' 查看Token使用统计")
        print("=" * 60)

        # 对话循环
        while True:
            print()
            user_input = input("你: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['quit', 'exit', '退出']:
                print("再见!")
                break

            if user_input.lower() == 'tools':
                print("\n可用工具:")
                for tool in agent.get_available_tools():
                    print(f"  • [{tool['type']}] {tool['name']}: {tool['description']}")
                continue

            if user_input.lower() == 'clear':
                agent.clear_history()
                print("历史已清除")
                continue

            if user_input.lower() == 'memory':
                # 先连接向量数据库
                if agent.react and agent.react.vector_memory:
                    agent.react.vector_memory.connect()
                
                stats = agent.get_memory_stats()
                if stats:
                    print("\n记忆状态:")
                    # 文本记忆
                    text_stats = stats.get('text_memory', {})
                    if text_stats:
                        print("  [文本记忆]")
                        print(f"    总对话轮数: {text_stats.get('total_turns', 0)}")
                        print(f"    当前窗口轮数: {text_stats.get('current_turns', 0)}")
                        print(f"    历史记忆块: {text_stats.get('memory_blocks', 0)}")
                        print(f"    总字数: {text_stats.get('total_chars', 0)}")

                    # 向量记忆
                    vector_stats = stats.get('vector_memory', {})
                    if vector_stats:
                        print("  [向量记忆]")
                        print(f"    总记录数: {vector_stats.get('total_count', 0)}")
                        print(f"    本地缓存: {vector_stats.get('local_cache_count', 0)}")
                        print(f"    连接状态: {'已连接' if vector_stats.get('connected') else '未连接'}")
                else:
                    print("\n暂无记忆")
                continue

            if user_input.lower().startswith('search '):
                query = user_input[7:].strip()
                if query:
                    results = agent.react.search_vector_memory(query, top_k=5)
                    if results:
                        print(f"\n找到 {len(results)} 条相似记忆:")
                        for i, result in enumerate(results, 1):
                            distance = result.get('distance', 0)
                            # 使用倒数转换将L2距离转为相似度分数 (0-1)
                            similarity = 1 / (1 + distance)
                            print(f"\n[{i}] 相似度: {similarity:.3f} (距离: {distance:.3f})")
                            print(f"    问题: {result.get('query', '')}")
                            print(f"    时间: {result.get('time', '未知')}")
                            if result.get('tool'):
                                print(f"    工具: {result.get('tool', '')}")
                            if result.get('content'):
                                print(f"    答案: {result.get('content', '')}")
                    else:
                        print("\n未找到相似记忆")
                continue

            if user_input.lower() == 'logs':
                from agent.logger import get_logger
                logger = get_logger()
                log_files = logger.get_log_files()
                print("\n日志文件路径:")
                print(f"  主日志: {log_files['log_file']}")
                print(f"  工具结果: {log_files['tool_results']}")
                print("\n日志内容包含:")
                print("  - 用户输入")
                print("  - 思考过程")
                print("  - 工具调用参数")
                print("  - 完整的工具返回结果（不截断）")
                continue

            if user_input.lower() == 'tokens':
                """查看 Token 使用统计"""
                if agent.react:
                    token_stats = agent.react.get_token_stats()
                    round_stats = token_stats.get('round', {})
                    session_stats = token_stats.get('session', {})

                    print("\nToken 使用统计:")
                    print("-" * 50)
                    print("  本轮对话:")
                    print(f"    输入: {round_stats.get('prompt_tokens', 0):,} tokens")
                    print(f"    输出: {round_stats.get('completion_tokens', 0):,} tokens")
                    print(f"    总计: {round_stats.get('total_tokens', 0):,} tokens")
                    print("  本次会话累计:")
                    print(f"    输入: {session_stats.get('prompt_tokens', 0):,} tokens")
                    print(f"    输出: {session_stats.get('completion_tokens', 0):,} tokens")
                    print(f"    总计: {session_stats.get('total_tokens', 0):,} tokens")
                    print("-" * 50)
                else:
                    print("ReAct 循环未初始化")
                continue

            # ========== MCP 管理命令 ==========
            if user_input.lower() == 'mcp list':
                """列出所有 MCP 服务器"""
                if agent.mcp:
                    servers = agent.mcp.list_mcp_servers()
                    print("\nMCP 服务器列表:")
                    print("-" * 80)
                    for server in servers:
                        status = "运行中" if server['running'] else ("已启用" if server['enabled'] else "已停用")
                        print(f"  [{status}] {server['name']}")
                        print(f"    命令: {server['command']}")
                        print(f"    参数: {' '.join(server['args'])}")
                        print()
                else:
                    print("MCP 管理器未初始化")
                continue

            if user_input.lower().startswith('mcp add '):
                """添加 MCP 服务器配置"""
                try:
                    # 格式: mcp add <name> <json_config>
                    parts = user_input[8:].strip().split(' ', 1)
                    if len(parts) != 2:
                        print("用法: mcp add <name> '{\"command\": \"...\", \"args\": [...]}'")
                        continue

                    name = parts[0]
                    config_str = parts[1]
                    config = json.loads(config_str)

                    if agent.mcp:
                        success, message = agent.mcp.add_mcp_server(name, config)
                        print(f"\n{'[OK]' if success else '[FAIL]'} {message}")
                    else:
                        print("MCP 管理器未初始化")
                except json.JSONDecodeError as e:
                    print(f"\n[FAIL] JSON 格式错误: {e}")
                except Exception as e:
                    print(f"\n[FAIL] 错误: {e}")
                continue

            if user_input.lower().startswith('mcp remove '):
                """删除 MCP 服务器配置"""
                name = user_input[11:].strip()
                if name:
                    if agent.mcp:
                        success, message = agent.mcp.remove_mcp_server(name)
                        print(f"\n{'[OK]' if success else '[FAIL]'} {message}")
                    else:
                        print("MCP 管理器未初始化")
                continue

            if user_input.lower().startswith('mcp enable '):
                """启用 MCP 服务器"""
                name = user_input[11:].strip()
                if name:
                    if agent.mcp:
                        success, message = agent.mcp.enable_mcp_server(name)
                        print(f"\n{'[OK]' if success else '[FAIL]'} {message}")
                    else:
                        print("MCP 管理器未初始化")
                continue

            if user_input.lower().startswith('mcp disable '):
                """停用 MCP 服务器"""
                name = user_input[12:].strip()
                if name:
                    if agent.mcp:
                        success, message = agent.mcp.disable_mcp_server(name)
                        print(f"\n{'[OK]' if success else '[FAIL]'} {message}")
                    else:
                        print("MCP 管理器未初始化")
                continue

            if user_input.lower().startswith('mcp start '):
                """启动 MCP 服务器"""
                name = user_input[10:].strip()
                if name:
                    if agent.mcp:
                        success, message = await agent.mcp.start_mcp_server(name)
                        print(f"\n{'[OK]' if success else '[FAIL]'} {message}")
                    else:
                        print("MCP 管理器未初始化")
                continue

            if user_input.lower().startswith('mcp stop '):
                """停止 MCP 服务器"""
                name = user_input[9:].strip()
                if name:
                    if agent.mcp:
                        success, message = await agent.mcp.stop_mcp_server(name)
                        print(f"\n{'[OK]' if success else '[FAIL]'} {message}")
                    else:
                        print("MCP 管理器未初始化")
                continue

            if user_input.lower().startswith('mcp disable-tool '):
                """禁用单个工具"""
                tool_name = user_input[17:].strip()
                if tool_name:
                    if agent.mcp:
                        success, message = agent.mcp.disable_tool(tool_name)
                        print(f"\n{'[OK]' if success else '[FAIL]'} {message}")
                    else:
                        print("MCP 管理器未初始化")
                continue

            if user_input.lower().startswith('mcp enable-tool '):
                """启用单个工具"""
                tool_name = user_input[16:].strip()
                if tool_name:
                    if agent.mcp:
                        success, message = agent.mcp.enable_tool(tool_name)
                        print(f"\n{'[OK]' if success else '[FAIL]'} {message}")
                    else:
                        print("MCP 管理器未初始化")
                continue

            if user_input.lower() == 'mcp disabled-tools':
                """列出被禁用的工具"""
                if agent.mcp:
                    disabled_tools = agent.mcp.list_disabled_tools()
                    if disabled_tools:
                        print("\n已禁用的工具:")
                        for tool in disabled_tools:
                            print(f"  - {tool}")
                    else:
                        print("\n没有禁用的工具")
                else:
                    print("MCP 管理器未初始化")
                continue

            if user_input.lower() == 'mcp help':
                """显示 MCP 管理帮助"""
                print("\nMCP 管理命令:")
                print("-" * 60)
                print("  mcp list              - 列出所有 MCP 服务器")
                print("  mcp add <name> <json> - 添加 MCP 服务器配置")
                print("  mcp remove <name>     - 删除 MCP 服务器配置")
                print("  mcp enable <name>          - 启用 MCP 服务器")
                print("  mcp disable <name>         - 停用 MCP 服务器")
                print("  mcp start <name>           - 启动 MCP 服务器")
                print("  mcp stop <name>            - 停止 MCP 服务器")
                print("  mcp disable-tool <name>    - 禁用单个工具")
                print("  mcp enable-tool <name>     - 启用单个工具")
                print("  mcp disabled-tools         - 列出被禁用的工具")
                print("  mcp help                   - 显示此帮助")
                print()
                print("示例:")
                print('  mcp add 12306 \'{"command": "python", "args": ["/path/to/12306.py"]}\'')
                continue

            # ========== Skill 管理命令 ==========
            if user_input.lower() == 'skill list':
                """列出所有 Skill"""
                if agent.skill:
                    skills = agent.skill.list_skills()
                    print("\nSkill 列表:")
                    print("-" * 80)
                    for skill in skills:
                        status = "启用" if skill['enabled'] else "停用"
                        loaded = "已加载" if skill['loaded'] else "未加载"
                        print(f"  [{status}] [{loaded}] {skill['name']}")
                    print()
                else:
                    print("Skill 管理器未初始化")
                continue

            if user_input.lower().startswith('skill add '):
                """添加 Skill"""
                try:
                    # 格式: skill add <source_dir> [skill_name]
                    parts = user_input[10:].strip().split(' ', 1)
                    source_dir = parts[0]
                    skill_name = parts[1] if len(parts) > 1 else None

                    if agent.skill:
                        success, message = agent.skill.add_skill(source_dir, skill_name)
                        print(f"\n{'[OK]' if success else '[FAIL]'} {message}")
                    else:
                        print("Skill 管理器未初始化")
                except Exception as e:
                    print(f"\n[FAIL] 错误: {e}")
                continue

            if user_input.lower().startswith('skill remove '):
                """删除 Skill"""
                name = user_input[13:].strip()
                if name:
                    if agent.skill:
                        success, message = agent.skill.remove_skill(name)
                        print(f"\n{'[OK]' if success else '[FAIL]'} {message}")
                    else:
                        print("Skill 管理器未初始化")
                continue

            if user_input.lower().startswith('skill enable '):
                """启用 Skill"""
                name = user_input[13:].strip()
                if name:
                    if agent.skill:
                        success, message = agent.skill.enable_skill(name)
                        print(f"\n{'[OK]' if success else '[FAIL]'} {message}")
                    else:
                        print("Skill 管理器未初始化")
                continue

            if user_input.lower().startswith('skill disable '):
                """停用 Skill"""
                name = user_input[14:].strip()
                if name:
                    if agent.skill:
                        success, message = agent.skill.disable_skill(name)
                        print(f"\n{'[OK]' if success else '[FAIL]'} {message}")
                    else:
                        print("Skill 管理器未初始化")
                continue

            if user_input.lower() == 'skill help':
                """显示 Skill 管理帮助"""
                print("\nSkill 管理命令:")
                print("-" * 60)
                print("  skill list                    - 列出所有 Skill")
                print("  skill add <source_dir> [name] - 添加 Skill（从目录复制）")
                print("  skill remove <name>           - 删除 Skill")
                print("  skill enable <name>           - 启用 Skill")
                print("  skill disable <name>          - 停用 Skill")
                print("  skill help                    - 显示此帮助")
                print()
                print("示例:")
                print('  skill add /path/to/my-skill    - 添加 skill，使用目录名作为 skill 名')
                print('  skill add /path/to/skill my-skill  - 添加 skill，指定 skill 名为 my-skill')
                print('  skill enable my-skill          - 启用 my-skill')
                print('  skill disable my-skill         - 停用 my-skill')
                continue

            try:
                # 运行智能体
                result = await agent.run(user_input)
                print(f"\n助手: {result}")

            except Exception as e:
                print(f"\n错误: {e}")
    
    except KeyboardInterrupt:
        print("\n\n再见!")
    
    except Exception as e:
        print(f"\n初始化错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        # 使用异步清理
        try:
            await agent.cleanup_async()
        except:
            # 如果异步清理失败，使用同步清理
            agent.cleanup()


if __name__ == "__main__":
    asyncio.run(main())