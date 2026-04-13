"""
启动 API 服务
"""

import os
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description="启动智能体 API 服务")
    parser.add_argument(
        "--host",
        default=os.getenv("API_HOST", "0.0.0.0"),
        help="服务主机地址 (默认: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("API_PORT", "8000")),
        help="服务端口 (默认: 8000)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="启用热重载（开发模式）"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="工作进程数 (默认: 1)"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("              智能体 API 服务")
    print("=" * 60)
    print(f"  主机: {args.host:<20} 端口: {args.port}")
    print(f"  热重载: {'启用' if args.reload else '禁用':<10} 工作进程: {args.workers}")
    print("-" * 60)
    print("  启动后访问:")
    print(f"    - API文档: http://{args.host}:{args.port}/docs")
    print(f"    - API地址: http://{args.host}:{args.port}")
    print("=" * 60)

    import uvicorn

    uvicorn.run(
        "api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else 1,
        log_level="info"
    )


if __name__ == "__main__":
    main()
