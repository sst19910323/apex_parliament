#!/bin/bash
# Start ONLY the FastAPI backend (apex_quant_entry).
# 数据下载 + 辩论调度 (data_scheduler / horizon_sentinel) 现在由 Claude Code 手动触发.
# 老版 ./start.sh 一次起三个的脚本仍保留, 不互相干扰.

cd /opt/apex_quant

VENV=./venv/bin/python
JOB="apex_quant_entry"
API_PORT=8001
HEALTH_WAIT_SEC=3

mkdir -p logs pids

PID_FILE="pids/$JOB.pid"

echo ">>> Starting $JOB (backend only) ..."

# Step 1: 检查是否已在跑 (PID 文件 + 实际进程双重确认)
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "⚠️  $JOB already running (PID: $(cat "$PID_FILE")). Skip."
    echo "   Run ./stop_backend.sh first to restart."
    exit 0
fi

# 删掉残留过期 PID 文件
[[ -f "$PID_FILE" ]] && rm -f "$PID_FILE"

# Step 2: 端口空闲检查 (防止 zombie 进程占住 8001 导致新进程秒崩)
if ss -ltn 2>/dev/null | grep -q ":${API_PORT}\b" || \
   netstat -ltn 2>/dev/null | grep -q ":${API_PORT}\b"; then
    echo "❌ NOT started: port $API_PORT is already bound by another process"
    echo "   Find owner: ss -ltnp | grep $API_PORT  (or lsof -i:$API_PORT)"
    exit 1
fi

# Step 3: 启动
nohup $VENV -u "$JOB.py" > "logs/$JOB.log" 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"

# Step 4: 立即验证 - 给 ${HEALTH_WAIT_SEC}s 启动时间, 再确认进程还活着
sleep $HEALTH_WAIT_SEC
if kill -0 "$PID" 2>/dev/null; then
    echo "✅ Started $JOB (PID: $PID) - listening on :$API_PORT"
else
    rm -f "$PID_FILE"
    echo "❌ $JOB died within ${HEALTH_WAIT_SEC}s of startup. Tail of logs/$JOB.log:"
    echo "----"
    tail -20 "logs/$JOB.log"
    echo "----"
    exit 1
fi

echo ">>> Done."
