#!/bin/sh
# 启动包装脚本，用于支持自动更新后的热重启
# 当 Python 进程退出代码为 1 时，代表更新完成请求拉起；由于 docker-compose 通常配置了 restart: always
# 此脚本保证退出后容器可以正确地被 Docker 守护进程重启拉起，从而应用新的代码逻辑。

echo "EmbyBoss: 正在启动 Python 进程..."
python3 main.py

exit_code=$?

if [ $exit_code -eq 1 ]; then
    echo "EmbyBoss: 检测到退出代码 1，代表需要热更新重启。正在退出容器以触发 Docker 重新拉起..."
    exit 1
elif [ $exit_code -eq 0 ]; then
    echo "EmbyBoss: 检测到正常退出请求。"
    exit 0
else
    echo "EmbyBoss: 检测到异常崩溃退出（代码: $exit_code），退出容器..."
    exit $exit_code
fi
