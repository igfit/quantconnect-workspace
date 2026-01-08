#!/bin/bash
# Run R18 backtests

run_backtest() {
    local PROJECT_ID=$1
    local NAME=$2

    echo "=== $NAME (Project $PROJECT_ID) ==="

    # Compile and get compileId
    COMPILE_OUTPUT=$(./scripts/qc-api.sh compile $PROJECT_ID 2>/dev/null)
    COMPILE_ID=$(echo "$COMPILE_OUTPUT" | grep '"compileId"' | head -1 | sed 's/.*"compileId": "\([^"]*\)".*/\1/')

    if [ -z "$COMPILE_ID" ]; then
        echo "ERROR: Compile failed"
        echo "$COMPILE_OUTPUT"
        return 1
    fi

    echo "CompileId: $COMPILE_ID"
    sleep 3

    # Run backtest
    BACKTEST_OUTPUT=$(./scripts/qc-api.sh backtest $PROJECT_ID "$NAME" "$COMPILE_ID" 2>/dev/null)
    BACKTEST_ID=$(echo "$BACKTEST_OUTPUT" | grep '"backtestId"' | head -1 | sed 's/.*"backtestId": "\([^"]*\)".*/\1/')

    if [ -z "$BACKTEST_ID" ]; then
        echo "ERROR: Backtest failed to start"
        echo "$BACKTEST_OUTPUT"
        return 1
    fi

    echo "BacktestId: $BACKTEST_ID"
    echo ""
}

# Run all three R18 backtests
run_backtest 27340538 "ResidualSmallCapR18"
sleep 5
run_backtest 27340540 "WeeklyKeltnerSmallCapR18"
sleep 5
run_backtest 27340544 "ResidualMidCapR18"

echo "All backtests started. Wait 30-60 seconds for results."
