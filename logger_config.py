"""
日志配置模块
提供详细的文件日志记录功能,不输出到控制台
"""

import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler


class CDPLogger:
    """CDP 连接器日志管理类"""
    
    def __init__(self, log_dir="logs", log_level=logging.DEBUG):
        """
        初始化日志系统
        
        Args:
            log_dir: 日志文件目录
            log_level: 日志级别 (默认 DEBUG)
        """
        self.log_dir = log_dir
        self.log_level = log_level
        self.logger = None
        self._setup_logger()
    
    def _setup_logger(self):
        """配置日志系统"""
        # 创建日志目录
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 生成日志文件名 (带时间戳)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(self.log_dir, f"cdp_connector_{timestamp}.log")
        
        # 创建 logger
        self.logger = logging.getLogger("CDPConnector")
        self.logger.setLevel(self.log_level)
        
        # 清除已有的 handlers (避免重复)
        if self.logger.handlers:
            self.logger.handlers.clear()
        
        # 创建文件 handler (带日志轮转)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(self.log_level)
        
        # 设置日志格式
        formatter = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        # 添加 handler
        self.logger.addHandler(file_handler)
        
        # 防止日志传播到根 logger (避免控制台输出)
        self.logger.propagate = False
        
        self.logger.info("=" * 80)
        self.logger.info("CDP 连接器日志系统已初始化")
        self.logger.info(f"日志文件: {log_file}")
        self.logger.info("=" * 80)
    
    def get_logger(self):
        """获取 logger 实例"""
        return self.logger
    
    def debug(self, message, **kwargs):
        """记录 DEBUG 级别日志"""
        self.logger.debug(message, extra=kwargs)
    
    def info(self, message, **kwargs):
        """记录 INFO 级别日志"""
        self.logger.info(message, extra=kwargs)
    
    def warning(self, message, **kwargs):
        """记录 WARNING 级别日志"""
        self.logger.warning(message, extra=kwargs)
    
    def error(self, message, exc_info=True, **kwargs):
        """记录 ERROR 级别日志"""
        self.logger.error(message, exc_info=exc_info, extra=kwargs)
    
    def critical(self, message, exc_info=True, **kwargs):
        """记录 CRITICAL 级别日志"""
        self.logger.critical(message, exc_info=exc_info, extra=kwargs)


# 全局日志实例 (单例模式)
_global_logger = None


def get_logger(log_dir="logs", log_level=logging.DEBUG):
    """
    获取全局日志实例
    
    Args:
        log_dir: 日志目录
        log_level: 日志级别
    
    Returns:
        CDPLogger 实例
    """
    global _global_logger
    if _global_logger is None:
        _global_logger = CDPLogger(log_dir=log_dir, log_level=log_level)
    return _global_logger
