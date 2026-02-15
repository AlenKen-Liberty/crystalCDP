#!/usr/bin/env python3
"""
快速测试脚本 - 验证代码语法和导入
"""

import sys

def test_imports():
    """测试模块导入"""
    print("测试模块导入...")
    
    try:
        from logger_config import get_logger
        print("✓ logger_config 导入成功")
    except Exception as e:
        print(f"✗ logger_config 导入失败: {e}")
        return False
    
    try:
        from stealth_config import StealthConfig
        print("✓ stealth_config 导入成功")
    except Exception as e:
        print(f"✗ stealth_config 导入失败: {e}")
        return False
    
    print("\n基础模块测试通过!")
    return True


def test_logger():
    """测试日志系统"""
    print("\n测试日志系统...")
    
    try:
        from logger_config import get_logger
        
        logger = get_logger(log_dir="test_logs")
        logger.info("这是一条测试日志")
        logger.debug("调试信息")
        logger.warning("警告信息")
        
        print("✓ 日志系统工作正常")
        print("  日志文件已创建在 test_logs/ 目录")
        return True
        
    except Exception as e:
        print(f"✗ 日志系统测试失败: {e}")
        return False


def test_stealth_config():
    """测试隐蔽性配置"""
    print("\n测试隐蔽性配置...")
    
    try:
        from stealth_config import StealthConfig
        
        print(f"  CDP 端点: {StealthConfig.CDP_ENDPOINT}")
        print(f"  延迟范围: {StealthConfig.DELAY_RANGE}")
        
        delay = StealthConfig.get_random_delay()
        print(f"  随机延迟: {delay:.3f}秒")
        
        print("✓ 隐蔽性配置正常")
        return True
        
    except Exception as e:
        print(f"✗ 隐蔽性配置测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("=" * 60)
    print("Crystal CDP - 模块测试")
    print("=" * 60)
    
    results = []
    
    # 测试导入
    results.append(test_imports())
    
    # 测试日志
    results.append(test_logger())
    
    # 测试配置
    results.append(test_stealth_config())
    
    # 总结
    print("\n" + "=" * 60)
    if all(results):
        print("✓ 所有测试通过!")
        print("\n注意: CDP 连接测试需要先启动 Chromium")
        print("启动命令: chromium --remote-debugging-port=9222")
        return 0
    else:
        print("✗ 部分测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
