#!/bin/bash
echo "=== CombinedBestLowDD ==="

CREATE_OUTPUT=$(./scripts/qc-api.sh project-create "CombinedBestLowDD" Py 2>/dev/null)
PROJECT_ID=$(echo "$CREATE_OUTPUT" | grep '"projectId"' | head -1 | sed 's/.*"projectId": \([0-9]*\).*/\1/')

if [ -z "$PROJECT_ID" ]; then
    echo "ERROR: Create failed"
    exit 1
fi

./scripts/qc-api.sh push $PROJECT_ID "algorithms/strategies/combined_best_lowdd.py" main.py 2>/dev/null | tail -1
sleep 2

COMPILE_OUTPUT=$(./scripts/qc-api.sh compile $PROJECT_ID 2>/dev/null)
COMPILE_ID=$(echo "$COMPILE_OUTPUT" | grep '"compileId"' | head -1 | sed 's/.*"compileId": "\([^"]*\)".*/\1/')

if [ -z "$COMPILE_ID" ]; then
    echo "ERROR: Compile failed"
    exit 1
fi
sleep 3

BACKTEST_OUTPUT=$(./scripts/qc-api.sh backtest $PROJECT_ID "CombinedBestLowDD" "$COMPILE_ID" 2>/dev/null)
BACKTEST_ID=$(echo "$BACKTEST_OUTPUT" | grep '"backtestId"' | head -1 | sed 's/.*"backtestId": "\([^"]*\)".*/\1/')

if [ -z "$BACKTEST_ID" ]; then
    echo "ERROR: Backtest failed"
    exit 1
fi

echo "ProjectId: $PROJECT_ID"
echo "BacktestId: $BACKTEST_ID"
