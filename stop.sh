#!/bin/bash
echo "=========================================="
echo "🛑 停止量化交易策略"
echo "=========================================="

pkill -f "main.py realtime" 2>/dev/null || true
pkill -f "main.py longterm" 2>/dev/null || true
pkill -f "main.py super" 2>/dev/null || true
pkill -f "main.py t0" 2>/dev/null || true
pkill -f "streamlit run dashboard" 2>/dev/null || true

echo "✅ 所有策略已停止"
echo "=========================================="
