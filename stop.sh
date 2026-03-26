#!/bin/bash

cd /opt/apex_quant

JOBS=("apex_quant_entry" "data_scheduler" "horizon_sentinel")

echo ">>> Stopping Apex Quant Services..."

for job in "${JOBS[@]}"; do
    PID_FILE="pids/$job.pid"

    if [[ -f "$PID_FILE" ]]; then
        PID=$(cat "$PID_FILE")
        
        # 检查进程是否活着
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            echo "🛑 Stopped $job (PID: $PID)"
            
            # 等待一秒，如果还活着就强杀 (可选)
            # sleep 1
            # kill -0 "$PID" 2>/dev/null && kill -9 "$PID"
        else
            echo "ℹ️  $job was not running."
        fi
        
        # 删掉 PID 文件
        rm "$PID_FILE"
    else
        echo "ℹ️  No PID file for $job"
    fi
done