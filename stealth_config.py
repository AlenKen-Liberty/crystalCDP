"""
隐蔽性配置模块
提供反检测措施和 Patchright 配置
"""

import random
import time


class StealthConfig:
    """隐蔽性配置类"""
    
    # CDP 连接配置
    CDP_ENDPOINT = "http://localhost:9222"
    
    # Patchright 连接选项
    CONNECT_OPTIONS = {
        # 超时设置
        "timeout": 60000,  # 60秒
        
        # 慢速模式 (更像人类操作)
        "slow_mo": 0,  # 初始设置为0,后续通过随机延迟实现
    }
    
    # 浏览器上下文选项 (最小化修改)
    CONTEXT_OPTIONS = {
        # 不覆盖 user-agent,使用浏览器原生的
        # "user_agent": None,
        
        # 不修改视口,使用浏览器当前设置
        # "viewport": None,
        
        # 保持现有的地理位置、权限等设置
        "bypass_csp": False,  # 不绕过 CSP
        "ignore_https_errors": False,  # 不忽略 HTTPS 错误
    }
    
    # 人性化延迟配置 (毫秒)
    DELAY_RANGE = {
        "min": 100,   # 最小延迟 100ms
        "max": 500,   # 最大延迟 500ms
    }
    
    # 页面操作超时 (毫秒)
    PAGE_TIMEOUT = {
        "navigation": 30000,  # 导航超时 30秒
        "wait_for": 10000,    # 等待元素超时 10秒
    }
    
    @staticmethod
    def get_random_delay():
        """
        获取随机延迟时间 (秒)
        模拟人类操作的不确定性
        
        Returns:
            float: 随机延迟时间 (秒)
        """
        delay_ms = random.randint(
            StealthConfig.DELAY_RANGE["min"],
            StealthConfig.DELAY_RANGE["max"]
        )
        return delay_ms / 1000.0
    
    @staticmethod
    def human_delay():
        """
        执行人性化延迟
        在操作之间添加随机延迟
        """
        delay = StealthConfig.get_random_delay()
        time.sleep(delay)
    
    @staticmethod
    def get_stealth_args():
        """
        获取 Patchright 的隐蔽性参数
        
        Returns:
            dict: 隐蔽性配置字典
        """
        return {
            # Patchright 特有的反检测参数
            # 注意: Patchright 默认已经包含很多反检测措施
            # 这里只需要最小化配置
            
            # 不注入自动化脚本
            "args": [],
            
            # 使用现有浏览器实例,不启动新的
            # (通过 connect_over_cdp 实现)
        }
    
    @staticmethod
    def get_page_options():
        """
        获取页面操作的默认选项
        
        Returns:
            dict: 页面操作选项
        """
        return {
            "timeout": StealthConfig.PAGE_TIMEOUT["wait_for"],
            "strict": True,  # 严格模式,确保选择器唯一
        }


# 反检测最佳实践提示
STEALTH_TIPS = """
隐蔽性最佳实践:

1. 连接策略:
   - 使用 connect_over_cdp() 连接到现有浏览器
   - 不要启动新的浏览器实例
   - 复用现有的用户配置和 cookies

2. 操作模式:
   - 在操作之间添加随机延迟
   - 避免快速连续的操作
   - 模拟人类的鼠标移动和滚动

3. 属性保护:
   - 不覆盖 navigator.userAgent
   - 不修改 navigator.webdriver (应该已经是 false)
   - 保持现有的浏览器指纹

4. 网络行为:
   - 使用浏览器原生的网络栈
   - 不修改请求头顺序
   - 保持 TLS 指纹一致

5. CDP 使用:
   - 最小化 CDP 命令的使用
   - 避免频繁的 DOM 查询
   - 使用高级 API 而非底层 CDP 命令
"""
