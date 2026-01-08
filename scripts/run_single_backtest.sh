#!/bin/bash
# Run a single backtest
PROJECT_ID=${1:-27340538}
NAME=${2:-"ResidualSmallCapR18"}

echo "=== Running $NAME (Project $PROJECT_ID) ==="

# Compile
COMPILE_OUTPUT=$(./scripts/qc-api.sh compile $PROJECT_ID 2>/dev/null)
COMPILE_ID=$(echo "$COMPILE_OUTPUT" | grep '"compileId"' | head -1 | sed 's/.*"compileId": "\([^"]*\)".*/\1/')

if [ -z "$COMPILE_ID" ]; then
    echo "ERROR: Compile failed"
    exit 1
fi

echo "CompileId: $COMPILE_ID"
sleep 3

# Run backtest
BACKTEST_OUTPUT=$(./scripts/qc-api.sh backtest $PROJECT_ID "$NAME" "$COMPILE_ID" 2>/dev/null)
BACKTEST_ID=$(echo "$BACKTEST_OUTPUT" | grep '"backtestId"' | head -1 | sed 's/.*"backtestId": "\([^"]*\)".*/\1/')

if [ -z "$BACKTEST_ID" ]; then
    echo "ERROR: Backtest failed"
    echo "$BACKTEST_OUTPUT" | head -20
    exit 1
fi

echo "BacktestId: $BACKTEST_ID"
echo "Waiting for completion..."

# Wait and poll for results
for i in {1..20}; do
    sleep 5
    RESULT=$(./scripts/qc-api.sh results $PROJECT_ID "$BACKTEST_ID" 2>/dev/null)
    COMPLETED=$(echo "$RESULT" | jq -r '.backtest.completed')

    if [ "$COMPLETED" == "true" ]; then
        echo ""
        echo "=== RESULTS ==="
        echo "$RESULT" | jq -r '.backtest.statistics | {
            "Sharpe Ratio": ."Sharpe Ratio",
            "CAGR": ."Compounding Annual Return",
            "Max Drawdown": ."Drawdown",
            "Net Profit": ."Net Profit",
            "Total Orders": ."Total Orders",
            "Win Rate": ."Win Rate",
            "Avg Win": ."Average Win",
            "Avg Loss": ."Average Loss"
        }'
        exit 0
    fi

    echo "Still running... ($i/20)"
done

echo "Timeout waiting for backtest"
