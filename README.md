# Crystal CDP - 隐蔽 CDP 连接器

基于 Patchright 的隐蔽 CDP 连接框架,用于连接本地 Chromium 浏览器。

## 功能特性

- ✅ 通过 CDP 协议连接到现有 Chromium 实例
- ✅ 保持隐蔽性,避免自动化检测
- ✅ 详细的文件日志记录
- ✅ 优雅的连接管理和错误处理
- ✅ 为 OpenClaw 集成预留接口

## 安装依赖

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Patchright 浏览器驱动
patchright install chromium
```

## 使用方法

### 1. 启动 Chromium 浏览器

首先,手动启动 Chromium 并启用远程调试:

```bash
# Linux
chromium --remote-debugging-port=9222 --user-data-dir=/path/to/your/profile

# 或者使用 Google Chrome
google-chrome --remote-debugging-port=9222 --user-data-dir=/path/to/your/profile
```

**重要参数说明:**
- `--remote-debugging-port=9222`: 启用 CDP 调试端口
- `--user-data-dir=/path/to/your/profile`: 指定用户数据目录 (保留登录状态和 cookies)

### 2. 运行 CDP 连接器

```bash
# 使用默认配置
python main.py

# 指定自定义 CDP 端点
python main.py --endpoint http://localhost:9223

# 指定日志目录
python main.py --log-dir ./my_logs
```

### 3. 查看日志

日志文件保存在 `logs/` 目录下,文件名格式: `cdp_connector_YYYYMMDD_HHMMSS.log`

```bash
# 查看最新日志
tail -f logs/cdp_connector_*.log
```

## 项目结构

```
crystalCDP/
├── main.py              # 主程序入口
├── cdp_connector.py     # CDP 连接管理器
├── logger_config.py     # 日志配置模块
├── stealth_config.py    # 隐蔽性配置模块
├── requirements.txt     # Python 依赖
├── README.md            # 本文件
└── logs/                # 日志文件目录 (自动创建)
```

## 核心模块说明

### logger_config.py
- 提供详细的文件日志记录
- 支持日志轮转 (单文件最大 10MB)
- 不输出到控制台,仅写入文件

### stealth_config.py
- 反检测配置
- 人性化延迟设置
- CDP 连接参数

### cdp_connector.py
- CDP 连接管理
- 页面获取和监控
- 连接保活机制

### main.py
- 命令行参数解析
- 信号处理 (Ctrl+C 优雅退出)
- 主程序流程控制

## 隐蔽性措施

本框架实现了以下反检测措施:

1. **使用 Patchright** - Playwright 的隐蔽性增强分支
2. **连接现有浏览器** - 不启动新实例,复用用户配置
3. **不覆盖属性** - 保持原生 user-agent 和浏览器指纹
4. **最小化干预** - 仅连接,不修改浏览器行为
5. **人性化延迟** - 操作间随机延迟 (100-500ms)

## 常见问题

### Q: 连接失败怎么办?

**A:** 检查以下几点:
1. Chromium 是否已启动并开启远程调试端口
2. 端口是否正确 (默认 9222)
3. 查看日志文件了解详细错误信息

### Q: 如何确认 Chromium 已正确启动?

**A:** 在浏览器中访问 `http://localhost:9222/json/version`,应该能看到浏览器信息。

### Q: 程序如何退出?

**A:** 按 `Ctrl+C` 即可优雅退出,程序会自动断开连接并保存日志。

### Q: 浏览器会被关闭吗?

**A:** 不会。程序只是断开连接,不会关闭你的浏览器。

## 与 OpenClaw 集成

本框架为 OpenClaw 集成预留了接口。OpenClaw 可以通过以下方式控制浏览器:

```python
from cdp_connector import create_connector

# 创建连接
connector = await create_connector()

# 获取活动页面
page = await connector.get_active_page()

# OpenClaw 可以使用 page 对象进行自动化操作
# 例如: await page.click("selector")
```

## 开发者信息

- **框架**: Patchright (Playwright fork)
- **协议**: Chrome DevTools Protocol (CDP)
- **Python 版本**: 3.7+

## 许可证

MIT License
