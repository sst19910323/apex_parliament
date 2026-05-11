#!/bin/bash
# Start Apex Quant services. 起前清场 + 启动后立刻验证存活 + 失败时打印 log 尾部

cd /opt/apex_quant

VENV=./venv/bin/python

mkdir -p logs pids

JOBS=("apex_quant_entry" "data_scheduler" "horizon_sentinel")
API_PORT=8001
API_JOB="apex_quant_entry"
HEALTH_WAIT_SEC=3   # 启动后等多久再验证存活

echo ">>> Starting Apex Quant Services..."

for job in "${JOBS[@]}"; do
    PID_FILE="pids/$job.pid"

    # Step 1: 检查是否真在跑 (不光看 PID 文件，还看实际进程)
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "⚠️  $job is already running (PID: $(cat "$PID_FILE")). Skip. (Run stop.sh first to restart)"
        continue
    fi

    # 删掉残留的过期 PID 文件
    [[ -f "$PID_FILE" ]] && rm -f "$PID_FILE"

    # Step 2: API 服务额外检查端口空闲 (防止 zombie 进程占住 8001)
    if [[ "$job" == "$API_JOB" ]]; then
        if ss -ltn 2>/dev/null | grep -q ":${API_PORT}\b" || \
           netstat -ltn 2>/dev/null | grep -q ":${API_PORT}\b"; then
            echo "❌ $job NOT started: port $API_PORT is already bound by another process"
            echo "   Find owner: ss -ltnp | grep $API_PORT  (or lsof -i:$API_PORT)"
            continue
        fi
    fi

    # Step 3: 启动
    nohup $VENV -u "$job.py" > "logs/$job.log" 2>&1 &
    PID=$!
    echo "$PID" > "$PID_FILE"

    # Step 4: 立即验证 - 给 ${HEALTH_WAIT_SEC}s 启动时间，再确认进程还活着
    sleep $HEALTH_WAIT_SEC
    if kill -0 "$PID" 2>/dev/null; then
        echo "✅ Started $job (PID: $PID)"
    else
        # 进程秒退，删掉 PID 文件 + 打印 log 尾部帮诊断
        rm -f "$PID_FILE"
        echo "❌ $job died within ${HEALTH_WAIT_SEC}s of startup. Tail of logs/$job.log:"
        echo "----"
        tail -20 "logs/$job.log"
        echo "----"
    fi
done

echo ">>> Done."
