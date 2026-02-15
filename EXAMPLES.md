# Crystal CDP - 使用示例

## 基础使用

### 1. 启动浏览器
```bash
chromium --remote-debugging-port=9222 --user-data-dir=~/chromium-profile
```

### 2. 运行连接器

**方式 A: 快速启动(推荐)**
```bash
./start.sh
```

**方式 B: 功能演示**
```bash
python3 demo.py
```

**方式 C: 直接运行**
```bash
python3 main.py
```

---

## 演示输出示例

```
============================================================
Crystal CDP - 功能演示
============================================================

正在连接到 Chromium...
✅ 连接成功!

📄 发现 1 个页面:

  [0] Reddit - The heart of the internet
      URL: https://www.reddit.com/

🎯 当前活动页面:
  标题: Reddit - The heart of the internet
  URL: https://www.reddit.com/

============================================================
✅ 演示完成!
============================================================
```

---

## OpenClaw 集成示例

```python
import asyncio
from cdp_connector import create_connector

async def openclaw_example():
    # 连接到浏览器
    connector = await create_connector()
    
    # 获取活动页面
    page = await connector.get_active_page()
    
    # 执行自动化操作
    # 例如: 点击、输入、提取内容等
    title = await page.title()
    content = await page.content()
    
    # 断开连接
    await connector.disconnect()

asyncio.run(openclaw_example())
```

---

## 可用脚本

| 脚本 | 用途 |
|------|------|
| `start.sh` | 快速启动(自动检测浏览器) |
| `demo.py` | 功能演示(显示页面信息) |
| `main.py` | 主程序(保活模式) |
| `test_modules.py` | 模块测试 |

---

## 查看日志

```bash
# 实时查看
tail -f logs/cdp_connector_*.log

# 查看最新日志
ls -lt logs/ | head -5
cat logs/cdp_connector_*.log
```
