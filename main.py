"""
CDP 连接器主程序
连接到本地 Chromium 并保持连接
"""

import asyncio
import argparse
import sys
import signal

from logger_config import get_logger
from cdp_connector import create_connector
from stealth_config import StealthConfig


class CDPMain:
    """主程序类"""
    
    def __init__(self, cdp_endpoint: str, log_dir: str = "logs"):
        """
        初始化主程序
        
        Args:
            cdp_endpoint: CDP 端点 URL
            log_dir: 日志目录
        """
        self.cdp_endpoint = cdp_endpoint
        self.log_dir = log_dir
        self.logger = None
        self.connector = None
        self.shutdown_event = asyncio.Event()
    
    def setup_logger(self):
        """初始化日志系统"""
        logger_instance = get_logger(log_dir=self.log_dir)
        self.logger = logger_instance.get_logger()
        self.logger.info("=" * 80)
        self.logger.info("CDP 连接器主程序启动")
        self.logger.info(f"CDP 端点: {self.cdp_endpoint}")
        self.logger.info(f"日志目录: {self.log_dir}")
        self.logger.info("=" * 80)
    
    def setup_signal_handlers(self):
        """设置信号处理器 (用于优雅退出)"""
        def signal_handler(signum, frame):
            self.logger.info(f"收到信号 {signum}, 准备退出...")
            self.shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def run(self):
        """运行主程序"""
        try:
            # 初始化日志
            self.setup_logger()
            
            # 设置信号处理
            self.setup_signal_handlers()
            
            # 创建并连接 CDP 连接器
            self.logger.info("正在创建 CDP 连接...")
            self.connector = await create_connector(self.cdp_endpoint)
            
            if not self.connector:
                self.logger.critical("无法连接到 Chromium, 程序退出")
                return 1
            
            self.logger.info("CDP 连接成功建立")
            
            # 获取当前活动页面
            active_page = await self.connector.get_active_page()
            if active_page:
                self.logger.info(f"当前活动页面: {active_page.url}")
            
            # 进入保活模式
            self.logger.info("进入保活模式, 按 Ctrl+C 退出")
            
            # 创建保活任务
            keep_alive_task = asyncio.create_task(
                self.connector.keep_alive(check_interval=5)
            )
            
            # 等待关闭信号
            shutdown_task = asyncio.create_task(self.shutdown_event.wait())
            
            # 等待任一任务完成
            done, pending = await asyncio.wait(
                [keep_alive_task, shutdown_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # 取消未完成的任务
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            # 断开连接
            self.logger.info("正在断开 CDP 连接...")
            await self.connector.disconnect()
            
            self.logger.info("程序正常退出")
            return 0
            
        except Exception as e:
            if self.logger:
                self.logger.critical(f"程序异常退出: {e}")
            else:
                print(f"严重错误: {e}", file=sys.stderr)
            return 1


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="CDP 连接器 - 连接到本地 Chromium 浏览器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 使用默认端点 (http://localhost:9222)
  python main.py
  
  # 指定自定义端点
  python main.py --endpoint http://localhost:9223
  
  # 指定日志目录
  python main.py --log-dir ./my_logs

注意:
  在运行此脚本前,请先启动 Chromium:
  chromium --remote-debugging-port=9222 --user-data-dir=/path/to/profile
        """
    )
    
    parser.add_argument(
        "--endpoint",
        type=str,
        default=StealthConfig.CDP_ENDPOINT,
        help=f"CDP 端点 URL (默认: {StealthConfig.CDP_ENDPOINT})"
    )
    
    parser.add_argument(
        "--log-dir",
        type=str,
        default="logs",
        help="日志文件目录 (默认: logs)"
    )
    
    return parser.parse_args()


def main():
    """主入口函数"""
    args = parse_args()
    
    # 创建主程序实例
    app = CDPMain(
        cdp_endpoint=args.endpoint,
        log_dir=args.log_dir
    )
    
    # 运行异步主程序
    exit_code = asyncio.run(app.run())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
