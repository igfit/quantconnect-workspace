#!/bin/bash
# Get project IDs for R18 strategies

TIMESTAMP=$(date +%s)
HASH=$(echo -n "${QC_API_TOKEN}:${TIMESTAMP}" | openssl dgst -sha256 | awk '{print $2}')
AUTH=$(echo -n "${QC_USER_ID}:${HASH}" | base64 -w 0)

curl -s -X GET "https://www.quantconnect.com/api/v2/projects/read" \
    -H "Authorization: Basic $AUTH" \
    -H "Timestamp: $TIMESTAMP" > /tmp/projects.json

# Extract R18 SmallCap/MidCap project IDs
jq -r '.projects[] | select(.name | test("SmallCap|MidCapR18")) | "\(.projectId) \(.name)"' /tmp/projects.json
