#!/bin/bash
# Stop Apex Quant services. 三段式杀: TERM -> wait -> KILL，再 pkill 兜底孤儿进程

cd /opt/apex_quant

JOBS=("apex_quant_entry" "data_scheduler" "horizon_sentinel")
TERM_WAIT_SEC=5   # 收到 TERM 后宽限时间，超时强杀

echo ">>> Stopping Apex Quant Services..."

kill_pid() {
    local pid="$1"
    local name="$2"

    if ! kill -0 "$pid" 2>/dev/null; then
        return 0  # 已经不在
    fi

    kill "$pid" 2>/dev/null
    # 等它优雅退出
    for i in $(seq 1 $TERM_WAIT_SEC); do
        sleep 1
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "🛑 $name (PID $pid) stopped gracefully (${i}s)"
            return 0
        fi
    done
    # 还活着，强杀
    kill -9 "$pid" 2>/dev/null
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
        echo "❌ $name (PID $pid) refused to die even with SIGKILL"
        return 1
    fi
    echo "💀 $name (PID $pid) force-killed (SIGKILL after ${TERM_WAIT_SEC}s timeout)"
    return 0
}

for job in "${JOBS[@]}"; do
    PID_FILE="pids/$job.pid"

    # Step 1: 用 PID 文件干掉记录的进程
    if [[ -f "$PID_FILE" ]]; then
        PID=$(cat "$PID_FILE")
        if [[ -n "$PID" ]]; then
            kill_pid "$PID" "$job"
        fi
        rm -f "$PID_FILE"
    else
        echo "ℹ️  No PID file for $job"
    fi

    # Step 2: pkill 兜底 — 抓 PID 文件没记录到的孤儿进程 (例如手动 nohup 起的)
    # -f 匹配完整命令行；用 "$job.py" 避免误伤其它进程
    ORPHAN_PIDS=$(pgrep -f "$job\.py" || true)
    if [[ -n "$ORPHAN_PIDS" ]]; then
        echo "⚠️  Found orphan process(es) for $job: $ORPHAN_PIDS, force-killing"
        for opid in $ORPHAN_PIDS; do
            kill_pid "$opid" "$job (orphan)"
        done
    fi
done

echo ">>> Done."
