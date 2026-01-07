#!/bin/bash
#
# QuantConnect API Helper Script
# Usage: ./scripts/qc-api.sh <command> [args...]
#
# Required environment variables:
#   QC_USER_ID    - Your QuantConnect user ID
#   QC_API_TOKEN  - Your QuantConnect API token
#

set -e

QC_BASE="https://www.quantconnect.com/api/v2"

# Check for required environment variables
check_auth() {
    if [[ -z "$QC_USER_ID" || -z "$QC_API_TOKEN" ]]; then
        echo "Error: QC_USER_ID and QC_API_TOKEN must be set"
        echo "Get these from: https://www.quantconnect.com/account"
        exit 1
    fi
}

# Make authenticated API call
qc_call() {
    local method="$1"
    local endpoint="$2"
    local data="$3"

    if [[ "$method" == "GET" ]]; then
        curl -s -X GET "$QC_BASE$endpoint" \
            -u "$QC_USER_ID:$QC_API_TOKEN"
    else
        curl -s -X POST "$QC_BASE$endpoint" \
            -u "$QC_USER_ID:$QC_API_TOKEN" \
            -H "Content-Type: application/json" \
            -d "$data"
    fi
}

# Pretty print JSON if jq is available
pp() {
    if command -v jq &> /dev/null; then
        jq "$@"
    else
        cat
    fi
}

case "$1" in
    auth|authenticate)
        # Test authentication
        check_auth
        echo "Testing authentication..."
        qc_call GET "/authenticate" | pp
        ;;

    projects|list)
        # List all projects
        check_auth
        qc_call GET "/projects/read" | pp '.projects[] | {id, name, modified, language}'
        ;;

    project-create)
        # Create a new project
        # Usage: qc-api.sh project-create "Project Name" [Python|CSharp]
        check_auth
        name="${2:-New Algorithm}"
        language="${3:-Python}"
        qc_call POST "/projects/create" "{\"name\":\"$name\",\"language\":\"$language\"}" | pp
        ;;

    files)
        # List files in a project
        # Usage: qc-api.sh files <projectId>
        check_auth
        if [[ -z "$2" ]]; then
            echo "Usage: $0 files <projectId>"
            exit 1
        fi
        qc_call POST "/files/read" "{\"projectId\":$2}" | pp '.files[] | {name, modified}'
        ;;

    file-read)
        # Read a specific file
        # Usage: qc-api.sh file-read <projectId> <filename>
        check_auth
        if [[ -z "$2" || -z "$3" ]]; then
            echo "Usage: $0 file-read <projectId> <filename>"
            exit 1
        fi
        qc_call POST "/files/read" "{\"projectId\":$2,\"name\":\"$3\"}" | pp '.files[0].content'
        ;;

    push|upload)
        # Upload/update a file in a project
        # Usage: qc-api.sh push <projectId> <local-file> [remote-name]
        check_auth
        if [[ -z "$2" || -z "$3" ]]; then
            echo "Usage: $0 push <projectId> <local-file> [remote-name]"
            exit 1
        fi
        projectId="$2"
        localFile="$3"
        remoteName="${4:-$(basename "$localFile")}"

        if [[ ! -f "$localFile" ]]; then
            echo "Error: File not found: $localFile"
            exit 1
        fi

        # Read file and escape for JSON
        content=$(cat "$localFile" | jq -Rs .)

        echo "Uploading $localFile as $remoteName to project $projectId..."
        qc_call POST "/files/update" "{\"projectId\":$projectId,\"name\":\"$remoteName\",\"content\":$content}" | pp
        ;;

    compile)
        # Compile a project
        # Usage: qc-api.sh compile <projectId>
        check_auth
        if [[ -z "$2" ]]; then
            echo "Usage: $0 compile <projectId>"
            exit 1
        fi
        echo "Compiling project $2..."
        qc_call POST "/compile/create" "{\"projectId\":$2}" | pp
        ;;

    backtest)
        # Run a backtest
        # Usage: qc-api.sh backtest <projectId> <name> [compileId]
        check_auth
        if [[ -z "$2" || -z "$3" ]]; then
            echo "Usage: $0 backtest <projectId> <name> [compileId]"
            exit 1
        fi
        projectId="$2"
        name="$3"
        compileId="${4:-}"

        echo "Starting backtest '$name' for project $projectId..."
        qc_call POST "/backtests/create" "{\"projectId\":$projectId,\"name\":\"$name\",\"compileId\":\"$compileId\"}" | pp
        ;;

    results|backtest-read)
        # Get backtest results
        # Usage: qc-api.sh results <projectId> <backtestId>
        check_auth
        if [[ -z "$2" || -z "$3" ]]; then
            echo "Usage: $0 results <projectId> <backtestId>"
            exit 1
        fi
        qc_call POST "/backtests/read" "{\"projectId\":$2,\"backtestId\":\"$3\"}" | pp
        ;;

    backtests-list)
        # List all backtests for a project
        # Usage: qc-api.sh backtests-list <projectId>
        check_auth
        if [[ -z "$2" ]]; then
            echo "Usage: $0 backtests-list <projectId>"
            exit 1
        fi
        qc_call POST "/backtests/read" "{\"projectId\":$2}" | pp '.backtests[] | {backtestId, name, completed, progress}'
        ;;

    live-list)
        # List live trading algorithms
        check_auth
        qc_call GET "/live/read" | pp
        ;;

    delete-backtest)
        # Delete a backtest
        # Usage: qc-api.sh delete-backtest <projectId> <backtestId>
        check_auth
        if [[ -z "$2" || -z "$3" ]]; then
            echo "Usage: $0 delete-backtest <projectId> <backtestId>"
            exit 1
        fi
        qc_call POST "/backtests/delete" "{\"projectId\":$2,\"backtestId\":\"$3\"}" | pp
        ;;

    help|--help|-h|"")
        echo "QuantConnect API Helper"
        echo ""
        echo "Usage: $0 <command> [args...]"
        echo ""
        echo "Commands:"
        echo "  auth                          Test API authentication"
        echo "  projects                      List all projects"
        echo "  project-create <name> [lang]  Create new project (Python/CSharp)"
        echo "  files <projectId>             List files in project"
        echo "  file-read <projId> <file>     Read file contents"
        echo "  push <projId> <file> [name]   Upload file to project"
        echo "  compile <projectId>           Compile project"
        echo "  backtest <projId> <name>      Run backtest"
        echo "  results <projId> <btId>       Get backtest results"
        echo "  backtests-list <projectId>    List all backtests"
        echo "  live-list                     List live algorithms"
        echo "  delete-backtest <pId> <btId>  Delete a backtest"
        echo ""
        echo "Environment variables required:"
        echo "  QC_USER_ID    - Your QuantConnect user ID"
        echo "  QC_API_TOKEN  - Your QuantConnect API token"
        echo ""
        echo "Examples:"
        echo "  $0 auth"
        echo "  $0 projects"
        echo "  $0 push 12345 algorithms/my-strategy/main.py"
        echo "  $0 backtest 12345 'Test Run 1'"
        ;;

    *)
        echo "Unknown command: $1"
        echo "Run '$0 help' for usage"
        exit 1
        ;;
esac
