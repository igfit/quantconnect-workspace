"""
QuantConnect API Runner

Handles all interactions with the QuantConnect API:
- Push code to projects
- Compile projects
- Run backtests
- Poll for completion
- Fetch results

Includes rate limiting, retry logic, and verbose output.
"""

import os
import time
import json
import hashlib
import base64
import subprocess
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
from dataclasses import dataclass, field

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


@dataclass
class BacktestResult:
    """Container for backtest result data"""
    backtest_id: str
    strategy_id: str
    name: str
    status: str
    success: bool
    error: Optional[str]
    statistics: Dict[str, Any]
    raw_response: Dict[str, Any]
    logs: List[str] = field(default_factory=list)
    runtime_errors: List[str] = field(default_factory=list)


class RateLimiter:
    """
    Adaptive rate limiter for API calls.

    Handles QC rate limits (30 req/min) with intelligent backoff
    when rate limit errors are detected.
    """

    def __init__(self, requests_per_minute: int = 20):
        self.requests_per_minute = requests_per_minute
        self.min_interval = 60.0 / requests_per_minute
        self.last_request_time = 0
        self.consecutive_rate_limits = 0
        self.base_wait = self.min_interval

    def wait(self):
        """Wait if necessary to respect rate limit"""
        elapsed = time.time() - self.last_request_time

        # Calculate wait time with backoff if we've hit rate limits
        wait_time = self.base_wait * (1.5 ** self.consecutive_rate_limits)

        if elapsed < wait_time:
            sleep_time = wait_time - elapsed
            if sleep_time > 1:
                print(f"    [Rate limit] Waiting {sleep_time:.1f}s...")
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    def report_rate_limit(self):
        """Called when a rate limit error is encountered"""
        self.consecutive_rate_limits += 1
        wait_time = 10 * (2 ** min(self.consecutive_rate_limits, 4))  # Cap at ~160s
        print(f"    [Rate limit HIT] Backing off for {wait_time}s (attempt {self.consecutive_rate_limits})")
        time.sleep(wait_time)

    def report_success(self):
        """Called when a request succeeds"""
        if self.consecutive_rate_limits > 0:
            self.consecutive_rate_limits = max(0, self.consecutive_rate_limits - 1)


class QCRunner:
    """
    QuantConnect API Runner

    Uses direct API calls with proper authentication.
    Includes verbose output and better error handling.
    """

    def __init__(self, project_id: int = None, verbose: bool = True):
        """
        Initialize the runner.

        Args:
            project_id: QuantConnect project ID to use (sandbox project)
            verbose: Whether to print detailed output
        """
        self.project_id = project_id or config.SANDBOX_PROJECT_ID
        self.verbose = verbose
        self.rate_limiter = RateLimiter(config.QC_RATE_LIMIT - config.QC_RATE_LIMIT_BUFFER)
        self.script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "scripts",
            "qc-api.sh"
        )

        # Get credentials from environment
        self.user_id = os.environ.get("QC_USER_ID")
        self.api_token = os.environ.get("QC_API_TOKEN")

        if not self.user_id or not self.api_token:
            raise ValueError("QC_USER_ID and QC_API_TOKEN must be set")

    def _log(self, msg: str, indent: int = 2):
        """Print message if verbose mode is on"""
        if self.verbose:
            print(" " * indent + msg)

    def _get_auth_headers(self) -> Dict[str, str]:
        """Generate authentication headers for QC API"""
        timestamp = str(int(time.time()))
        hash_input = f"{self.api_token}:{timestamp}"
        hash_hex = hashlib.sha256(hash_input.encode()).hexdigest()
        auth_string = f"{self.user_id}:{hash_hex}"
        auth_b64 = base64.b64encode(auth_string.encode()).decode()

        return {
            "Authorization": f"Basic {auth_b64}",
            "Timestamp": timestamp,
            "Content-Type": "application/json"
        }

    def _is_rate_limit_error(self, error_msg: str) -> bool:
        """Check if error is a rate limit error"""
        rate_limit_phrases = [
            "too many",
            "rate limit",
            "slow down",
            "throttl",
            "429"
        ]
        error_lower = str(error_msg).lower()
        return any(phrase in error_lower for phrase in rate_limit_phrases)

    def _api_call_direct(
        self,
        method: str,
        endpoint: str,
        data: Dict[str, Any] = None,
        retries: int = 5
    ) -> Dict[str, Any]:
        """
        Make a direct API call to QuantConnect.

        Args:
            method: HTTP method (GET or POST)
            endpoint: API endpoint
            data: JSON data for POST requests
            retries: Number of retries

        Returns:
            Parsed JSON response
        """
        self.rate_limiter.wait()

        url = f"{config.QC_API_BASE}{endpoint}"
        headers = self._get_auth_headers()

        for attempt in range(retries):
            try:
                if method == "GET":
                    req = urllib.request.Request(url, headers=headers, method="GET")
                else:
                    body = json.dumps(data).encode() if data else None
                    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

                with urllib.request.urlopen(req, timeout=60) as response:
                    result = json.loads(response.read().decode())
                    self.rate_limiter.report_success()
                    return result

            except urllib.error.HTTPError as e:
                error_body = e.read().decode() if e.fp else str(e)

                # Check for rate limit
                if self._is_rate_limit_error(error_body) or e.code == 429:
                    self.rate_limiter.report_rate_limit()
                    continue

                if attempt < retries - 1:
                    wait = 2 ** (attempt + 1)
                    self._log(f"HTTP error {e.code}, retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"API call failed: {e.code} - {error_body}")

            except urllib.error.URLError as e:
                if attempt < retries - 1:
                    wait = 2 ** (attempt + 1)
                    self._log(f"Network error, retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"Network error: {e.reason}")

            except Exception as e:
                if attempt < retries - 1:
                    wait = 2 ** (attempt + 1)
                    time.sleep(wait)
                    continue
                raise

        raise RuntimeError("API call failed after all retries")

    def test_auth(self) -> bool:
        """Test API authentication"""
        try:
            response = self._api_call_direct("GET", "/authenticate")
            return response.get("success", False)
        except Exception as e:
            print(f"Auth test failed: {e}")
            return False

    def list_projects(self) -> Dict[str, Any]:
        """List all projects"""
        return self._api_call_direct("GET", "/projects/read")

    def create_project(self, name: str, language: str = "Py") -> Dict[str, Any]:
        """
        Create a new project.

        Args:
            name: Project name
            language: "Py" or "C#"

        Returns:
            Response containing projectId
        """
        return self._api_call_direct("POST", "/projects/create", {
            "name": name,
            "language": language
        })

    def get_or_create_sandbox_project(self, name: str = "Strategy Factory Sandbox") -> int:
        """
        Get existing sandbox project or create new one.

        Returns:
            Project ID
        """
        # List existing projects
        response = self.list_projects()

        if response.get("success") and "projects" in response:
            for project in response["projects"]:
                if project.get("name") == name:
                    project_id = project["projectId"]
                    print(f"Found existing sandbox project: {project_id}")
                    self.project_id = project_id
                    return project_id

        # Create new project
        print(f"Creating new sandbox project: {name}")
        response = self.create_project(name)

        if response.get("success") and "projects" in response:
            project_id = response["projects"][0]["projectId"]
            self.project_id = project_id
            return project_id

        raise RuntimeError(f"Failed to create sandbox project: {response}")

    def push_code(self, code: str, filename: str = "main.py") -> Dict[str, Any]:
        """
        Push code to the project.

        Args:
            code: Python code to push
            filename: Target filename in project

        Returns:
            API response
        """
        if not self.project_id:
            raise ValueError("No project ID set. Call get_or_create_sandbox_project first.")

        return self._api_call_direct("POST", "/files/update", {
            "projectId": self.project_id,
            "name": filename,
            "content": code
        })

    def compile_project(self) -> Tuple[bool, Optional[str], List[str]]:
        """
        Compile the project.

        Returns:
            (success, compile_id or error message, list of errors/warnings)
        """
        if not self.project_id:
            raise ValueError("No project ID set.")

        response = self._api_call_direct("POST", "/compile/create", {
            "projectId": self.project_id
        })

        errors = response.get("errors", [])
        logs = response.get("logs", [])

        if response.get("success"):
            compile_id = response.get("compileId")
            state = response.get("state", "Unknown")
            self._log(f"Compile state: {state}")
            if logs:
                for log in logs[:3]:
                    self._log(f"  {log}", indent=4)
            return True, compile_id, errors + logs
        else:
            error_msg = "; ".join(errors) if errors else "Unknown compilation error"
            self._log(f"Compile FAILED: {error_msg}")
            return False, error_msg, errors

    def run_backtest(
        self,
        name: str,
        compile_id: str = None
    ) -> Tuple[bool, Optional[str], List[str]]:
        """
        Start a backtest.

        Args:
            name: Backtest name
            compile_id: Compile ID (if None, will compile first)

        Returns:
            (success, backtest_id or error message, errors list)
        """
        if not self.project_id:
            raise ValueError("No project ID set.")

        # Compile if no compile_id provided
        if compile_id is None:
            success, result, compile_errors = self.compile_project()
            if not success:
                return False, f"Compilation failed: {result}", compile_errors
            compile_id = result

        # Run backtest
        response = self._api_call_direct("POST", "/backtests/create", {
            "projectId": self.project_id,
            "backtestName": name,
            "compileId": compile_id
        })

        errors = response.get("errors", [])

        if response.get("success"):
            # backtestId is inside the backtest object
            backtest = response.get("backtest", {})
            backtest_id = backtest.get("backtestId")
            return True, backtest_id, errors
        else:
            error_msg = "; ".join(errors) if errors else "Unknown backtest error"

            # Check for rate limit
            if self._is_rate_limit_error(error_msg):
                self.rate_limiter.report_rate_limit()

            return False, error_msg, errors

    def get_backtest_status(self, backtest_id: str) -> Dict[str, Any]:
        """Get backtest status and results"""
        if not self.project_id:
            raise ValueError("No project ID set.")

        return self._api_call_direct("POST", "/backtests/read", {
            "projectId": self.project_id,
            "backtestId": backtest_id
        })

    def wait_for_backtest(
        self,
        backtest_id: str,
        timeout: int = None,
        poll_interval: int = None
    ) -> Dict[str, Any]:
        """
        Wait for backtest to complete with progress output.

        Args:
            backtest_id: Backtest ID to wait for
            timeout: Max seconds to wait
            poll_interval: Seconds between polls

        Returns:
            Final backtest results
        """
        if timeout is None:
            timeout = config.BACKTEST_TIMEOUT
        if poll_interval is None:
            poll_interval = config.BACKTEST_POLL_INTERVAL

        start_time = time.time()
        last_progress = ""

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                raise TimeoutError(f"Backtest timed out after {timeout}s")

            response = self.get_backtest_status(backtest_id)

            # Check if complete
            if response.get("success"):
                backtest = response.get("backtest", {})
                progress = backtest.get("progress", 0)

                # Show progress updates
                progress_str = f"{progress:.0%}" if isinstance(progress, float) else str(progress)
                if progress_str != last_progress:
                    self._log(f"Progress: {progress_str}", indent=4)
                    last_progress = progress_str

                # QuantConnect uses "completed" field or we check for statistics
                if backtest.get("completed") or (progress == 1 and backtest.get("statistics")):
                    return response

                # Check for errors in the backtest
                if backtest.get("error"):
                    self._log(f"Backtest error: {backtest.get('error')}", indent=4)
                    return response

                if backtest.get("stacktrace"):
                    self._log(f"Stack trace detected", indent=4)
                    return response

            # Wait before next poll
            time.sleep(poll_interval)

    def run_full_backtest(
        self,
        code: str,
        strategy_id: str,
        backtest_name: str = None
    ) -> BacktestResult:
        """
        Run a complete backtest: push, compile, run, wait, return results.

        Includes verbose output and better error handling.

        Args:
            code: Python code to backtest
            strategy_id: Strategy ID for tracking
            backtest_name: Name for the backtest

        Returns:
            BacktestResult with all data including logs
        """
        if backtest_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backtest_name = f"{strategy_id}_{timestamp}"

        # Step 1: Push code
        self._log("Pushing code...")
        push_response = self.push_code(code)
        if not push_response.get("success"):
            error_msg = str(push_response.get("errors", "Push failed"))
            self._log(f"Push FAILED: {error_msg}")
            return BacktestResult(
                backtest_id="",
                strategy_id=strategy_id,
                name=backtest_name,
                status="push_failed",
                success=False,
                error=error_msg,
                statistics={},
                raw_response=push_response,
                runtime_errors=[error_msg]
            )

        # Step 2: Compile
        self._log("Compiling...")
        success, compile_result, compile_logs = self.compile_project()
        if not success:
            self._log(f"Compile FAILED: {compile_result}")
            for log in compile_logs[:5]:  # Show first 5 errors
                self._log(f"  - {log}", indent=4)
            return BacktestResult(
                backtest_id="",
                strategy_id=strategy_id,
                name=backtest_name,
                status="compile_failed",
                success=False,
                error=compile_result,
                statistics={},
                raw_response={"compile_error": compile_result},
                logs=compile_logs,
                runtime_errors=compile_logs
            )

        # Step 3: Start backtest (with retry for rate limits)
        self._log("Starting backtest...")
        max_attempts = 3
        for attempt in range(max_attempts):
            success, backtest_id, bt_errors = self.run_backtest(backtest_name, compile_result)

            if success:
                break
            elif self._is_rate_limit_error(str(backtest_id)):
                if attempt < max_attempts - 1:
                    self._log(f"Rate limited, attempt {attempt + 2}/{max_attempts}...")
                    continue
            else:
                self._log(f"Backtest start FAILED: {backtest_id}")
                return BacktestResult(
                    backtest_id="",
                    strategy_id=strategy_id,
                    name=backtest_name,
                    status="backtest_start_failed",
                    success=False,
                    error=str(backtest_id),
                    statistics={},
                    raw_response={"backtest_error": backtest_id},
                    runtime_errors=bt_errors
                )

        if not success:
            return BacktestResult(
                backtest_id="",
                strategy_id=strategy_id,
                name=backtest_name,
                status="rate_limited",
                success=False,
                error="Rate limited after multiple attempts",
                statistics={},
                raw_response={},
                runtime_errors=["Rate limited"]
            )

        # Step 4: Wait for completion
        self._log(f"Waiting for completion (backtest_id: {backtest_id})...")
        try:
            response = self.wait_for_backtest(backtest_id)
        except TimeoutError as e:
            return BacktestResult(
                backtest_id=backtest_id,
                strategy_id=strategy_id,
                name=backtest_name,
                status="timeout",
                success=False,
                error=str(e),
                statistics={},
                raw_response={}
            )

        # Step 5: Extract results and logs
        backtest_data = response.get("backtest", {})
        statistics = backtest_data.get("statistics", {})
        logs = backtest_data.get("logs", [])
        runtime_errors = []

        # Check for runtime errors
        if backtest_data.get("error"):
            runtime_errors.append(backtest_data.get("error"))
            self._log(f"Runtime error: {backtest_data.get('error')}", indent=4)
        if backtest_data.get("stacktrace"):
            trace = backtest_data.get('stacktrace')[:500]
            runtime_errors.append(f"Stack trace: {trace}")
            self._log(f"Stack trace: {trace[:200]}...", indent=4)

        # Check for 0 trades and report
        total_orders = statistics.get("Total Orders", "0")
        if str(total_orders) == "0":
            self._log("WARNING: 0 trades generated!", indent=4)
            # Try to get more info
            runtime_stats = backtest_data.get("runtimeStatistics", {})
            if runtime_stats:
                self._log(f"Runtime stats: {json.dumps(runtime_stats, indent=2)[:200]}", indent=4)

        # Show key statistics
        self._log(f"Results: Sharpe={statistics.get('Sharpe Ratio', 'N/A')}, "
                  f"CAGR={statistics.get('Compounding Annual Return', 'N/A')}, "
                  f"Trades={total_orders}", indent=4)

        return BacktestResult(
            backtest_id=backtest_id,
            strategy_id=strategy_id,
            name=backtest_name,
            status="completed",
            success=True,
            error=None,
            statistics=statistics,
            raw_response=response,
            logs=logs,
            runtime_errors=runtime_errors
        )

    def validate_strategy_execution(self, result: BacktestResult) -> Dict[str, Any]:
        """
        Validate that a strategy actually executed properly.

        Returns:
            Dict with validation results and diagnostics
        """
        validation = {
            "valid": True,
            "issues": [],
            "warnings": [],
            "diagnostics": {}
        }

        # Check for compile/runtime errors
        if not result.success:
            validation["valid"] = False
            validation["issues"].append(f"Backtest failed: {result.error}")
            return validation

        # Check for 0 trades
        total_trades = result.statistics.get("Total Orders", "0")
        try:
            trade_count = int(str(total_trades).replace(",", ""))
        except:
            trade_count = 0

        if trade_count == 0:
            validation["valid"] = False
            validation["issues"].append("Strategy generated 0 trades")
            validation["diagnostics"]["possible_causes"] = [
                "Entry conditions never met (thresholds too restrictive)",
                "Indicators not ready during backtest period",
                "AND conditions requiring multiple signals simultaneously",
                "Universe symbols may not have data for the period",
                "Price/volume filters excluding all candidates"
            ]

        # Check for runtime errors
        if result.runtime_errors:
            validation["warnings"].extend(result.runtime_errors)

        # Check for negative Sharpe
        sharpe = result.statistics.get("Sharpe Ratio", "0")
        try:
            sharpe_val = float(sharpe)
            if sharpe_val < -1:
                validation["warnings"].append(f"Very negative Sharpe ratio: {sharpe_val}")
        except:
            pass

        # Check drawdown
        drawdown = result.statistics.get("Drawdown", "0%")
        try:
            dd_val = float(str(drawdown).replace("%", ""))
            if dd_val > 50:
                validation["warnings"].append(f"High drawdown: {dd_val}%")
        except:
            pass

        return validation


def get_runner(project_id: int = None, verbose: bool = True) -> QCRunner:
    """Get a configured QCRunner instance"""
    return QCRunner(project_id, verbose)


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    print("Testing QC API Runner...")

    runner = QCRunner(verbose=True)

    # Test auth
    print("\n1. Testing authentication...")
    if runner.test_auth():
        print("   Auth successful!")
    else:
        print("   Auth failed!")
        exit(1)

    # List projects
    print("\n2. Listing projects...")
    projects = runner.list_projects()
    if projects.get("success"):
        print(f"   Found {len(projects.get('projects', []))} projects")
    else:
        print(f"   Failed: {projects}")

    # Get or create sandbox
    print("\n3. Getting/creating sandbox project...")
    try:
        project_id = runner.get_or_create_sandbox_project()
        print(f"   Sandbox project ID: {project_id}")
    except Exception as e:
        print(f"   Failed: {e}")

    print("\nRunner test complete!")
