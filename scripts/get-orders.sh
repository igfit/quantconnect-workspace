#!/bin/bash
# Fetch orders for a backtest

PROJECT_ID="$1"
BACKTEST_ID="$2"
START="${3:-0}"
END="${4:-100}"

timestamp=$(date +%s)
hash=$(echo -n "${QC_API_TOKEN}:${timestamp}" | openssl dgst -sha256 | awk '{print $2}')
auth=$(echo -n "${QC_USER_ID}:${hash}" | base64 -w 0)

curl -s -X POST "https://www.quantconnect.com/api/v2/backtests/orders/read" \
    -H "Authorization: Basic $auth" \
    -H "Timestamp: $timestamp" \
    -H "Content-Type: application/json" \
    -d "{\"projectId\": $PROJECT_ID, \"backtestId\": \"$BACKTEST_ID\", \"start\": $START, \"end\": $END}"
