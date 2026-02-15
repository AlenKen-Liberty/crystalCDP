# 快速使用指南

## 1. 安装依赖

```bash
cd /home/ubuntu/scripts/crystalCDP

# 安装 Python 包 (可能需要几分钟)
pip install -r requirements.txt

# 安装 Patchright 浏览器驱动
patchright install chromium
```

## 2. 启动 Chromium

```bash
# 方式 1: 使用 Chromium
chromium --remote-debugging-port=9222 --user-data-dir=~/chromium-profile

# 方式 2: 使用 Google Chrome
google-chrome --remote-debugging-port=9222 --user-data-dir=~/chrome-profile
```

**重要:** 启动后在浏览器中登录 Reddit

## 3. 运行连接器

```bash
# 方式 1: 使用快速启动脚本 (推荐)
./start.sh

# 方式 2: 直接运行
python3 main.py

# 方式 3: 自定义参数
python3 main.py --endpoint http://localhost:9222 --log-dir ./logs
```

## 4. 查看日志

```bash
# 实时查看日志
tail -f logs/cdp_connector_*.log

# 查看完整日志
cat logs/cdp_connector_*.log
```

## 5. 退出程序

按 `Ctrl+C` 优雅退出,浏览器会保持运行

---

## 验证连接

访问 `http://localhost:9222/json/version` 应该能看到浏览器信息

---

## 故障排查

**问题: 连接失败**
- 确认 Chromium 已启动
- 检查端口 9222 是否被占用
- 查看日志文件了解详细错误

**问题: Patchright 安装慢**
- 这是正常的,需要下载浏览器驱动
- 请耐心等待几分钟
