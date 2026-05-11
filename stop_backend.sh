#!/bin/bash
# Stop ONLY the FastAPI backend (apex_quant_entry).
# 不会动 data_scheduler / horizon_sentinel; 老版 ./stop.sh 仍保留管那些.

cd /opt/apex_quant

JOB="apex_quant_entry"
PID_FILE="pids/$JOB.pid"
TERM_WAIT_SEC=5

echo ">>> Stopping $JOB (backend only) ..."

kill_pid() {
    local pid="$1"
    local label="$2"

    if ! kill -0 "$pid" 2>/dev/null; then
        return 0
    fi

    kill "$pid" 2>/dev/null
    for i in $(seq 1 $TERM_WAIT_SEC); do
        sleep 1
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "🛑 $label (PID $pid) stopped gracefully (${i}s)"
            return 0
        fi
    done

    kill -9 "$pid" 2>/dev/null
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
        echo "❌ $label (PID $pid) refused to die even with SIGKILL"
        return 1
    fi
    echo "💀 $label (PID $pid) force-killed (SIGKILL after ${TERM_WAIT_SEC}s timeout)"
    return 0
}

# Step 1: 用 PID 文件干掉记录的进程
if [[ -f "$PID_FILE" ]]; then
    PID=$(cat "$PID_FILE")
    if [[ -n "$PID" ]]; then
        kill_pid "$PID" "$JOB"
    fi
    rm -f "$PID_FILE"
else
    echo "ℹ️  No PID file for $JOB"
fi

# Step 2: pkill 兜底, 抓 PID 文件没记录到的孤儿进程
ORPHAN_PIDS=$(pgrep -f "${JOB}\.py" || true)
if [[ -n "$ORPHAN_PIDS" ]]; then
    echo "⚠️  Found orphan process(es): $ORPHAN_PIDS, force-killing"
    for opid in $ORPHAN_PIDS; do
        kill_pid "$opid" "$JOB (orphan)"
    done
fi

echo ">>> Done."
