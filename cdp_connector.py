"""
CDP 连接器核心模块
管理与 Chromium 的 CDP 连接
"""

import asyncio
from typing import Optional, List
from patchright.async_api import async_playwright, Browser, BrowserContext, Page

from logger_config import get_logger
from stealth_config import StealthConfig


class CDPConnector:
    """CDP 连接管理器"""
    
    def __init__(self, cdp_endpoint: str = None):
        """
        初始化 CDP 连接器
        
        Args:
            cdp_endpoint: CDP 端点 URL (默认 http://localhost:9222)
        """
        self.cdp_endpoint = cdp_endpoint or StealthConfig.CDP_ENDPOINT
        self.logger = get_logger().get_logger()
        
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.contexts: List[BrowserContext] = []
        self.pages: List[Page] = []
        
        self.logger.info(f"CDP 连接器已初始化, 端点: {self.cdp_endpoint}")
    
    async def connect(self):
        """
        连接到现有的 Chromium 实例
        
        Returns:
            bool: 连接是否成功
        """
        try:
            self.logger.info("开始连接到 Chromium...")
            
            # 启动 Playwright
            self.playwright = await async_playwright().start()
            self.logger.debug("Playwright 已启动")
            
            # 连接到现有浏览器 (通过 CDP)
            self.browser = await self.playwright.chromium.connect_over_cdp(
                self.cdp_endpoint,
                timeout=StealthConfig.CONNECT_OPTIONS["timeout"]
            )
            self.logger.info("已成功连接到 Chromium 浏览器")
            
            # 获取现有的上下文
            self.contexts = self.browser.contexts
            self.logger.info(f"发现 {len(self.contexts)} 个浏览器上下文")
            
            # 获取所有页面
            for idx, context in enumerate(self.contexts):
                context_pages = context.pages
                self.pages.extend(context_pages)
                self.logger.info(f"上下文 {idx}: {len(context_pages)} 个页面")
                
                # 记录每个页面的 URL
                for page_idx, page in enumerate(context_pages):
                    try:
                        url = page.url
                        self.logger.debug(f"  页面 {page_idx}: {url}")
                    except Exception as e:
                        self.logger.warning(f"  页面 {page_idx}: 无法获取 URL - {e}")
            
            self.logger.info(f"总共发现 {len(self.pages)} 个页面")
            
            if not self.pages:
                self.logger.warning("警告: 未发现任何打开的页面")
            
            return True
            
        except Exception as e:
            self.logger.error(f"连接到 Chromium 失败: {e}")
            return False
    
    async def get_active_page(self) -> Optional[Page]:
        """
        获取当前活动的页面
        
        Returns:
            Page: 活动页面对象,如果没有则返回 None
        """
        try:
            if not self.pages:
                self.logger.warning("没有可用的页面")
                return None
            
            # 尝试获取最后一个页面 (通常是当前活动的)
            active_page = self.pages[-1]
            url = active_page.url
            self.logger.info(f"当前活动页面: {url}")
            
            return active_page
            
        except Exception as e:
            self.logger.error(f"获取活动页面失败: {e}")
            return None
    
    async def get_all_pages(self) -> List[Page]:
        """
        获取所有页面
        
        Returns:
            List[Page]: 所有页面对象列表
        """
        return self.pages
    
    async def wait_for_new_page(self, timeout: int = 30000) -> Optional[Page]:
        """
        等待新页面打开 (例如点击链接后)
        
        Args:
            timeout: 超时时间 (毫秒)
        
        Returns:
            Page: 新打开的页面,如果超时则返回 None
        """
        try:
            self.logger.info("等待新页面打开...")
            
            if not self.contexts:
                self.logger.error("没有可用的浏览器上下文")
                return None
            
            # 在第一个上下文中等待新页面
            context = self.contexts[0]
            
            async def wait_for_page():
                return await context.wait_for_event("page", timeout=timeout)
            
            new_page = await wait_for_page()
            self.pages.append(new_page)
            
            url = new_page.url
            self.logger.info(f"检测到新页面: {url}")
            
            return new_page
            
        except asyncio.TimeoutError:
            self.logger.warning(f"等待新页面超时 ({timeout}ms)")
            return None
        except Exception as e:
            self.logger.error(f"等待新页面失败: {e}")
            return None
    
    async def refresh_pages(self):
        """
        刷新页面列表 (检测新打开或关闭的页面)
        """
        try:
            self.logger.debug("刷新页面列表...")
            
            old_count = len(self.pages)
            self.pages.clear()
            
            for context in self.contexts:
                self.pages.extend(context.pages)
            
            new_count = len(self.pages)
            
            if old_count != new_count:
                self.logger.info(f"页面数量变化: {old_count} -> {new_count}")
            
        except Exception as e:
            self.logger.error(f"刷新页面列表失败: {e}")
    
    async def disconnect(self):
        """
        断开 CDP 连接
        """
        try:
            self.logger.info("开始断开连接...")
            
            if self.browser:
                # 注意: 不要关闭浏览器,只是断开连接
                # self.browser.close() 会关闭用户的浏览器!
                self.logger.info("已断开浏览器连接 (浏览器保持运行)")
                self.browser = None
            
            if self.playwright:
                await self.playwright.stop()
                self.logger.debug("Playwright 已停止")
                self.playwright = None
            
            self.contexts.clear()
            self.pages.clear()
            
            self.logger.info("CDP 连接已完全断开")
            
        except Exception as e:
            self.logger.error(f"断开连接时出错: {e}")
    
    async def keep_alive(self, check_interval: int = 5):
        """
        保持连接活跃,定期检查连接状态
        
        Args:
            check_interval: 检查间隔 (秒)
        """
        self.logger.info(f"进入保活模式 (检查间隔: {check_interval}秒)")
        
        try:
            while True:
                await asyncio.sleep(check_interval)
                
                # 检查浏览器连接
                if not self.browser or not self.browser.is_connected():
                    self.logger.error("浏览器连接已断开!")
                    break
                
                # 刷新页面列表
                await self.refresh_pages()
                
                self.logger.debug(f"连接正常, 当前 {len(self.pages)} 个页面")
                
        except KeyboardInterrupt:
            self.logger.info("收到中断信号,退出保活模式")
        except Exception as e:
            self.logger.error(f"保活模式异常: {e}")


# 便捷函数
async def create_connector(cdp_endpoint: str = None) -> Optional[CDPConnector]:
    """
    创建并连接 CDP 连接器
    
    Args:
        cdp_endpoint: CDP 端点 URL
    
    Returns:
        CDPConnector: 已连接的连接器实例,失败则返回 None
    """
    connector = CDPConnector(cdp_endpoint)
    
    if await connector.connect():
        return connector
    else:
        return None
