"""
QuantConnect API Runner

Handles all interactions with the QuantConnect API:
- Push code to projects
- Compile projects
- Run backtests
- Poll for completion
- Fetch results

Includes rate limiting and retry logic.
"""

import os
import time
import json
import hashlib
import base64
import subprocess
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

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


class RateLimiter:
    """Simple rate limiter for API calls"""

    def __init__(self, requests_per_minute: int):
        self.requests_per_minute = requests_per_minute
        self.min_interval = 60.0 / requests_per_minute
        self.last_request_time = 0

    def wait(self):
        """Wait if necessary to respect rate limit"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_interval:
            sleep_time = self.min_interval - elapsed
            time.sleep(sleep_time)
        self.last_request_time = time.time()


class QCRunner:
    """
    QuantConnect API Runner

    Uses direct API calls with proper authentication.
    """

    def __init__(self, project_id: int = None):
        """
        Initialize the runner.

        Args:
            project_id: QuantConnect project ID to use (sandbox project)
        """
        self.project_id = project_id or config.SANDBOX_PROJECT_ID
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

    def _api_call_direct(
        self,
        method: str,
        endpoint: str,
        data: Dict[str, Any] = None,
        retries: int = 3
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
                    return json.loads(response.read().decode())

            except urllib.error.HTTPError as e:
                error_body = e.read().decode() if e.fp else str(e)
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"API call failed: {e.code} - {error_body}")

            except urllib.error.URLError as e:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"Network error: {e.reason}")

            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise

        raise RuntimeError("API call failed after all retries")

    def _call_api(self, *args, retries: int = 3) -> Dict[str, Any]:
        """
        Call the QC API via qc-api.sh script.

        Args:
            args: Arguments to pass to qc-api.sh
            retries: Number of retries on failure

        Returns:
            Parsed JSON response
        """
        self.rate_limiter.wait()

        cmd = [self.script_path] + list(args)

        for attempt in range(retries):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode != 0:
                    if attempt < retries - 1:
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    raise RuntimeError(f"API call failed: {result.stderr}")

                # Parse JSON response
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    # Try to find JSON in output (script may print extra text)
                    output = result.stdout.strip()
                    # Find first { and last } to extract JSON
                    start_idx = output.find('{')
                    end_idx = output.rfind('}')
                    if start_idx != -1 and end_idx != -1:
                        json_str = output[start_idx:end_idx + 1]
                        return json.loads(json_str)
                    raise ValueError(f"Invalid JSON response: {output[:200]}")

            except subprocess.TimeoutExpired:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
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

    def compile_project(self) -> Tuple[bool, Optional[str]]:
        """
        Compile the project.

        Returns:
            (success, compile_id or error message)
        """
        if not self.project_id:
            raise ValueError("No project ID set.")

        response = self._api_call_direct("POST", "/compile/create", {
            "projectId": self.project_id
        })

        if response.get("success"):
            compile_id = response.get("compileId")
            return True, compile_id
        else:
            errors = response.get("errors", [])
            error_msg = "; ".join(errors) if errors else "Unknown compilation error"
            return False, error_msg

    def run_backtest(
        self,
        name: str,
        compile_id: str = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Start a backtest.

        Args:
            name: Backtest name
            compile_id: Compile ID (if None, will compile first)

        Returns:
            (success, backtest_id or error message)
        """
        if not self.project_id:
            raise ValueError("No project ID set.")

        # Compile if no compile_id provided
        if compile_id is None:
            success, result = self.compile_project()
            if not success:
                return False, f"Compilation failed: {result}"
            compile_id = result

        # Run backtest
        response = self._api_call_direct("POST", "/backtests/create", {
            "projectId": self.project_id,
            "backtestName": name,
            "compileId": compile_id
        })

        if response.get("success"):
            # backtestId is inside the backtest object
            backtest = response.get("backtest", {})
            backtest_id = backtest.get("backtestId")
            return True, backtest_id
        else:
            errors = response.get("errors", [])
            error_msg = "; ".join(errors) if errors else "Unknown backtest error"
            return False, error_msg

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
        Wait for backtest to complete.

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

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                raise TimeoutError(f"Backtest timed out after {timeout}s")

            response = self.get_backtest_status(backtest_id)

            # Check if complete
            if response.get("success"):
                backtest = response.get("backtest", {})
                # QuantConnect uses "completed" field or we check for statistics
                if backtest.get("completed") or backtest.get("statistics"):
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

        Args:
            code: Python code to backtest
            strategy_id: Strategy ID for tracking
            backtest_name: Name for the backtest

        Returns:
            BacktestResult with all data
        """
        if backtest_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backtest_name = f"{strategy_id}_{timestamp}"

        print(f"  Pushing code...")
        push_response = self.push_code(code)
        if not push_response.get("success"):
            return BacktestResult(
                backtest_id="",
                strategy_id=strategy_id,
                name=backtest_name,
                status="push_failed",
                success=False,
                error=str(push_response.get("errors", "Push failed")),
                statistics={},
                raw_response=push_response
            )

        print(f"  Compiling...")
        success, compile_result = self.compile_project()
        if not success:
            return BacktestResult(
                backtest_id="",
                strategy_id=strategy_id,
                name=backtest_name,
                status="compile_failed",
                success=False,
                error=compile_result,
                statistics={},
                raw_response={"compile_error": compile_result}
            )

        print(f"  Starting backtest...")
        success, backtest_id = self.run_backtest(backtest_name, compile_result)
        if not success:
            return BacktestResult(
                backtest_id="",
                strategy_id=strategy_id,
                name=backtest_name,
                status="backtest_start_failed",
                success=False,
                error=backtest_id,
                statistics={},
                raw_response={"backtest_error": backtest_id}
            )

        print(f"  Waiting for completion (backtest_id: {backtest_id})...")
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

        # Extract statistics
        backtest_data = response.get("backtest", {})
        statistics = backtest_data.get("statistics", {})

        return BacktestResult(
            backtest_id=backtest_id,
            strategy_id=strategy_id,
            name=backtest_name,
            status="completed",
            success=True,
            error=None,
            statistics=statistics,
            raw_response=response
        )


def get_runner(project_id: int = None) -> QCRunner:
    """Get a configured QCRunner instance"""
    return QCRunner(project_id)


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    print("Testing QC API Runner...")

    runner = QCRunner()

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
