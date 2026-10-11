#!/usr/bin/env python3
"""
GenuDo Testing Engine Bootstrapper:
Cross-platform environment detector and setup orchestrator for macOS, Linux, and Windows.
Provisions Python virtual environment, installs dependencies, and verifies GenuDo credentials.
"""

import os
import sys
import shutil
import platform
import subprocess

def log(msg, prefix="[*]"):
    print(f"{prefix} {msg}", flush=True)

def get_platform():
    s = platform.system().lower()
    if "darwin" in s:
        return "macos"
    elif "windows" in s:
        return "windows"
    return "linux"

def find_binary(cmd):
    return shutil.which(cmd)

def check_dependencies():
    plat = get_platform()
    log(f"Detected Platform: {plat} ({platform.platform()})")

    # 1. Python check
    py_bin = sys.executable
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    log(f"Current Python: {py_bin} (v{py_ver})")
    if sys.version_info < (3, 9):
        log("Python 3.9 or higher is required!", prefix="[!]")
        if plat == "macos":
            log("To upgrade: brew install python@3.10")
        elif plat == "linux":
            log("To upgrade: sudo apt-get update && sudo apt-get install -y python3.10 python3.10-venv")
        elif plat == "windows":
            log("To upgrade: winget install Python.Python.3.10 or download from https://python.org")
        sys.exit(1)

    # 2. Git check
    git_path = find_binary("git")
    if not git_path:
        log("Git was not found on your system PATH.", prefix="[!]")
        if plat == "macos":
            log("Run: xcode-select --install")
        elif plat == "linux":
            log("Run: sudo apt-get install -y git")
        elif plat == "windows":
            log("Run: winget install Git.Git")
        sys.exit(1)
    else:
        log(f"Git found: {git_path}")

    # 3. Node.js check (optional but recommended)
    node_path = find_binary("node")
    if not node_path:
        log("Node.js not detected (optional, required only for npm CLI commands).", prefix="[i]")
    else:
        log(f"Node.js found: {node_path}")

    return plat

def setup_virtualenv(repo_root):
    venv_dir = os.path.join(repo_root, ".venv")
    is_win = platform.system().lower() == "windows"
    py_venv = os.path.join(venv_dir, "Scripts", "python.exe") if is_win else os.path.join(venv_dir, "bin", "python")
    pip_venv = os.path.join(venv_dir, "Scripts", "pip.exe") if is_win else os.path.join(venv_dir, "bin", "pip")

    if not os.path.exists(venv_dir):
        log(f"Creating Python virtual environment in {venv_dir}...")
        subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)
    else:
        log(f"Virtual environment already exists in {venv_dir}.")

    req_file = os.path.join(repo_root, "requirements.txt")
    if os.path.exists(req_file):
        log("Installing/upgrading dependencies from requirements.txt...")
        subprocess.run([py_venv, "-m", "pip", "install", "--upgrade", "pip"], check=True)
        subprocess.run([py_venv, "-m", "pip", "install", "-r", req_file], check=True)
    else:
        log("requirements.txt not found, skipping pip install.", prefix="[i]")

    return py_venv

def verify_genudo_config(repo_root):
    env_file = os.path.join(repo_root, ".env")
    if not os.path.exists(env_file) and not os.environ.get("GENUDO_TOKEN"):
        example = os.path.join(repo_root, ".env.example")
        if os.path.exists(example):
            log("No .env file found. Copying .env.example -> .env...")
            shutil.copyfile(example, env_file)
            log("Please edit .env and insert your GENUDO_TOKEN before executing tests.", prefix="[!]")
        else:
            log("Please set the GENUDO_TOKEN environment variable.", prefix="[!]")
    else:
        log("GenuDo configuration found.")

def main():
    repo_root = os.path.dirname(os.path.abspath(__file__))
    log(f"Bootstrapping GenuDo Testing Engine in: {repo_root}")
    check_dependencies()
    py_bin = setup_virtualenv(repo_root)
    verify_genudo_config(repo_root)
    log("Setup complete! You can now run tests with:", prefix="[+]")
    log(f"  {py_bin} src/engine.py run --dry-run")

if __name__ == "__main__":
    main()
