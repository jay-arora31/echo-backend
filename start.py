"""Entry point to run both the FastAPI backend and LiveKit Voice Agent."""

import subprocess
import sys
import signal
import os
import platform
from pathlib import Path

# Load .env file FIRST before starting any subprocess
from dotenv import load_dotenv
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)
print(f"✅ Loaded environment from: {env_path}")


def kill_port(port: int):
    """Kill any process running on the specified port."""
    system = platform.system()
    
    try:
        if system == "Darwin" or system == "Linux":
            # macOS/Linux: Use lsof to find and kill process
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True
            )
            if result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    if pid:
                        print(f"   Killing process {pid} on port {port}...")
                        subprocess.run(["kill", "-9", pid], capture_output=True)
                print(f"   Port {port} cleared")
                return True
        elif system == "Windows":
            # Windows: Use netstat and taskkill
            result = subprocess.run(
                ["netstat", "-ano", "|", "findstr", f":{port}"],
                capture_output=True,
                text=True,
                shell=True
            )
            if result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        print(f"   Killing process {pid} on port {port}...")
                        subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
                print(f"   Port {port} cleared")
                return True
    except Exception as e:
        print(f"   Could not check port {port}: {e}")
    
    return False


def main():
    print("=" * 50)
    print("Starting SuperBryn Voice Agent")
    print("=" * 50)
    print()
    
    # Kill any existing process on ports 8000 and 8081
    print("0. Checking ports...")
    if not kill_port(8000):
        print("   Port 8000 is available")
    if not kill_port(8081):
        print("   Port 8081 is available")
    print()
    
    print("1. Starting FastAPI backend (port 8000)...")
    print("2. Starting LiveKit Voice Agent worker...")
    print()
    
    # Get current environment (includes loaded .env vars)
    env = os.environ.copy()
    cwd = os.path.dirname(os.path.abspath(__file__))
    
    # Start FastAPI server
    fastapi_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
        cwd=cwd,
        env=env,
    )
    
    # Start Voice Agent worker
    # The LiveKit CLI needs the 'start' command passed via sys.argv
    agent_process = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.argv = ['agent', 'start']; from app.agent.voice_agent import run_agent; run_agent()"],
        cwd=cwd,
        env=env,
    )
    
    print()
    print("=" * 50)
    print("Both services started!")
    print("- API: http://localhost:8000")
    print("- API Docs: http://localhost:8000/docs")
    print("- Voice Agent: Connected to LiveKit")
    print("=" * 50)
    print()
    print("Press Ctrl+C to stop both services...")
    print()
    
    def signal_handler(sig, frame):
        print()
        print("Shutting down...")
        fastapi_process.terminate()
        agent_process.terminate()
        fastapi_process.wait()
        agent_process.wait()
        print("Services stopped.")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Wait for processes
    try:
        fastapi_process.wait()
        agent_process.wait()
    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == "__main__":
    main()
