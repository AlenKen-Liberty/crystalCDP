#!/bin/bash
# Crystal CDP 快速启动脚本

echo "======================================"
echo "Crystal CDP - 快速启动"
echo "======================================"
echo ""

# 检查 Chromium 是否在运行
if curl -s http://localhost:9222/json/version > /dev/null 2>&1; then
    echo "✓ 检测到 Chromium 正在运行 (端口 9222)"
    echo ""
    
    # 显示浏览器信息
    echo "浏览器信息:"
    curl -s http://localhost:9222/json/version | python3 -m json.tool
    echo ""
    
    # 启动连接器
    echo "启动 CDP 连接器..."
    python3 main.py
else
    echo "✗ 未检测到 Chromium 实例"
    echo ""
    echo "请先启动 Chromium:"
    echo "  chromium --remote-debugging-port=9222 --user-data-dir=~/chromium-profile"
    echo ""
    echo "或者使用 Google Chrome:"
    echo "  google-chrome --remote-debugging-port=9222 --user-data-dir=~/chrome-profile"
    echo ""
    exit 1
fi
