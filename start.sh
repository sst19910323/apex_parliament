#!/bin/bash

# 1. 确保进入项目目录
cd /opt/apex_quant

# 2. 指定 Python 解释器 (根据你的环境调整，如果是 venv 就在这里)
# 如果不是 venv，可以直接写 python3
VENV=./venv/bin/python

# 3. 准备目录
mkdir -p logs pids

# 4. 要启动的三个任务
JOBS=("apex_quant_entry" "data_scheduler" "horizon_sentinel")

echo ">>> Starting Apex Quant Services..."

for job in "${JOBS[@]}"; do
    PID_FILE="pids/$job.pid"

    # 检查是否已运行
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "⚠️  $job is already running (PID: $(cat "$PID_FILE"))"
        continue
    fi

    # 启动!
    # -u: 禁用缓存，让日志实时刷出来
    nohup $VENV -u "$job.py" > "logs/$job.log" 2>&1 &
    
    # 记录 PID
    PID=$!
    echo $PID > "$PID_FILE"
    echo "✅ Started $job (PID: $PID)"
done