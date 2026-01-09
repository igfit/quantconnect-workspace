#!/bin/bash
# Run V4 and LargeCap Low DD backtests

run_strategy() {
    local NAME=$1
    local FILE=$2

    echo "=== Creating project: $NAME ==="

    CREATE_OUTPUT=$(./scripts/qc-api.sh project-create "$NAME" Py 2>/dev/null)
    PROJECT_ID=$(echo "$CREATE_OUTPUT" | grep '"projectId"' | head -1 | sed 's/.*"projectId": \([0-9]*\).*/\1/')

    if [ -z "$PROJECT_ID" ]; then
        echo "ERROR: Failed to create project"
        return 1
    fi
    echo "ProjectId: $PROJECT_ID"

    ./scripts/qc-api.sh push $PROJECT_ID "$FILE" main.py 2>/dev/null | tail -1
    sleep 2

    COMPILE_OUTPUT=$(./scripts/qc-api.sh compile $PROJECT_ID 2>/dev/null)
    COMPILE_ID=$(echo "$COMPILE_OUTPUT" | grep '"compileId"' | head -1 | sed 's/.*"compileId": "\([^"]*\)".*/\1/')

    if [ -z "$COMPILE_ID" ]; then
        echo "ERROR: Compile failed"
        return 1
    fi
    echo "CompileId: $COMPILE_ID"
    sleep 3

    BACKTEST_OUTPUT=$(./scripts/qc-api.sh backtest $PROJECT_ID "$NAME" "$COMPILE_ID" 2>/dev/null)
    BACKTEST_ID=$(echo "$BACKTEST_OUTPUT" | grep '"backtestId"' | head -1 | sed 's/.*"backtestId": "\([^"]*\)".*/\1/')

    if [ -z "$BACKTEST_ID" ]; then
        echo "ERROR: Backtest failed"
        echo "$BACKTEST_OUTPUT" | head -10
        return 1
    fi
    echo "BacktestId: $BACKTEST_ID"
    echo "$PROJECT_ID $BACKTEST_ID $NAME" >> /tmp/lowdd_v4.txt
    echo ""
}

> /tmp/lowdd_v4.txt

run_strategy "SmallCapLowDD_V4" "algorithms/strategies/smallcap_low_dd_v4.py"
sleep 5
run_strategy "LargeCapLowDD" "algorithms/strategies/largecap_low_dd.py"

echo "=== Backtests started ==="
cat /tmp/lowdd_v4.txt
