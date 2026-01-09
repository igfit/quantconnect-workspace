#!/bin/bash
# Run small-cap V6-V9 strategies

run_strategy() {
    local NAME=$1
    local FILE=$2

    echo "=== $NAME ==="

    CREATE_OUTPUT=$(./scripts/qc-api.sh project-create "$NAME" Py 2>/dev/null)
    PROJECT_ID=$(echo "$CREATE_OUTPUT" | grep '"projectId"' | head -1 | sed 's/.*"projectId": \([0-9]*\).*/\1/')

    if [ -z "$PROJECT_ID" ]; then
        echo "ERROR: Create failed"
        return 1
    fi

    ./scripts/qc-api.sh push $PROJECT_ID "$FILE" main.py 2>/dev/null | tail -1
    sleep 2

    COMPILE_OUTPUT=$(./scripts/qc-api.sh compile $PROJECT_ID 2>/dev/null)
    COMPILE_ID=$(echo "$COMPILE_OUTPUT" | grep '"compileId"' | head -1 | sed 's/.*"compileId": "\([^"]*\)".*/\1/')

    if [ -z "$COMPILE_ID" ]; then
        echo "ERROR: Compile failed"
        return 1
    fi
    sleep 3

    BACKTEST_OUTPUT=$(./scripts/qc-api.sh backtest $PROJECT_ID "$NAME" "$COMPILE_ID" 2>/dev/null)
    BACKTEST_ID=$(echo "$BACKTEST_OUTPUT" | grep '"backtestId"' | head -1 | sed 's/.*"backtestId": "\([^"]*\)".*/\1/')

    if [ -z "$BACKTEST_ID" ]; then
        echo "ERROR: Backtest failed"
        echo "$BACKTEST_OUTPUT" | head -5
        return 1
    fi
    echo "ProjectId: $PROJECT_ID, BacktestId: $BACKTEST_ID"
    echo "$PROJECT_ID $BACKTEST_ID $NAME" >> /tmp/smallcap_v6v9.txt
    echo ""
}

> /tmp/smallcap_v6v9.txt

run_strategy "SmallCapV6Trend" "algorithms/strategies/smallcap_v6_trend.py"
sleep 8
run_strategy "SmallCapV7RelStrength" "algorithms/strategies/smallcap_v7_relstrength.py"
sleep 8
run_strategy "SmallCapV8VolContract" "algorithms/strategies/smallcap_v8_volcontract.py"
sleep 8
run_strategy "SmallCapV9NearHigh" "algorithms/strategies/smallcap_v9_nearhigh.py"

echo "=== All Started ==="
cat /tmp/smallcap_v6v9.txt
