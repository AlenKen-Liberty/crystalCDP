#!/usr/bin/env python3
"""
完整功能演示脚本
展示如何使用 CDP 连接器获取页面信息
"""

import asyncio
import sys
from cdp_connector import create_connector
from logger_config import get_logger


async def demo():
    """演示 CDP 连接器功能"""
    
    # 初始化日志
    logger = get_logger(log_dir="logs")
    log = logger.get_logger()
    
    print("=" * 60)
    print("Crystal CDP - 功能演示")
    print("=" * 60)
    print()
    
    # 创建连接
    print("正在连接到 Chromium...")
    connector = await create_connector()
    
    if not connector:
        print("❌ 连接失败!")
        print("请确保 Chromium 已启动:")
        print("  chromium --remote-debugging-port=9222")
        return 1
    
    print("✅ 连接成功!")
    print()
    
    # 获取所有页面
    pages = await connector.get_all_pages()
    print(f"📄 发现 {len(pages)} 个页面:")
    print()
    
    for idx, page in enumerate(pages):
        try:
            url = page.url
            title = await page.title()
            print(f"  [{idx}] {title}")
            print(f"      URL: {url}")
            print()
        except Exception as e:
            log.warning(f"无法获取页面 {idx} 信息: {e}")
    
    # 获取活动页面
    active_page = await connector.get_active_page()
    if active_page:
        print("🎯 当前活动页面:")
        try:
            title = await active_page.title()
            url = active_page.url
            print(f"  标题: {title}")
            print(f"  URL: {url}")
            print()
        except Exception as e:
            log.warning(f"无法获取活动页面信息: {e}")
    
    # 演示完成
    print("=" * 60)
    print("✅ 演示完成!")
    print("=" * 60)
    print()
    print("提示:")
    print("  - 所有操作已记录到日志文件")
    print("  - 查看日志: tail -f logs/cdp_connector_*.log")
    print("  - OpenClaw 可以使用 page 对象进行自动化操作")
    print()
    
    # 断开连接
    await connector.disconnect()
    
    return 0


def main():
    """主函数"""
    try:
        exit_code = asyncio.run(demo())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n中断退出")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
