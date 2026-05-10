#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "📈 A股量化交易系统启动"
echo "=========================================="

MODE="${1:-realtime}"

case $MODE in
    realtime|longterm|super|t0|dashboard)
        python3 main.py "$MODE"
        ;;
    all)
        echo "启动短线策略..."
        nohup python3 main.py realtime > logs/realtime.log 2>&1 &
        echo "短线策略已启动 (PID: $!)"
        echo ""
        echo "查看日志: tail -f logs/realtime.log"
        echo "停止: ./stop.sh"
        ;;
    *)
        echo "用法: $0 {realtime|longterm|super|t0|dashboard|all}"
        echo ""
        echo "  realtime  - 短线套利策略"
        echo "  longterm  - 长线价值策略"
        echo "  super     - 超级策略(AI驱动)"
        echo "  t0        - ETF T+0日内策略"
        echo "  dashboard - Streamlit看板"
        echo "  all       - 启动所有策略(后台)"
        exit 1
        ;;
esac
