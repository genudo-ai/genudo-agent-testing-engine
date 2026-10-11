"""
Configuration and Environment Management for GenuDo Testing Engine.
"""

import os
import sys

def load_dotenv(dotenv_path=None):
    if dotenv_path is None:
        dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(dotenv_path):
        return
    with open(dotenv_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            if key not in os.environ:
                os.environ[key] = val

load_dotenv()

GENUDO_BASE = os.environ.get("GENUDO_BASE", "https://api.genudo.ai").rstrip("/")
GENUDO_TOKEN = os.environ.get("GENUDO_TOKEN", "")
GENUDO_ENV = os.environ.get("GENUDO_ENV", "dev").lower()
GENUDO_ARCHIVED_STAGE = os.environ.get("GENUDO_ARCHIVED_STAGE", "Archived")
MCP_MAX_RPM = int(os.environ.get("GENUDO_MCP_MAX_RPM", "30"))

def get_pipelines():
    """Parse GENUDO_PIPELINES ("channel=pipeline_id,channel=pipeline_id") into {channel: id}."""
    raw = os.environ.get("GENUDO_PIPELINES", "")
    mapping = {}
    for part in raw.split(","):
        part = part.strip()
        if "=" in part:
            ch, pid = part.split("=", 1)
            try:
                mapping[ch.strip().lower()] = int(pid.strip())
            except ValueError:
                sys.exit(f"GENUDO_PIPELINES: '{part}' is not channel=<numeric pipeline id> (e.g. messenger=12345).")
    return mapping

def check_prod_safety(allow_prod_flag=False):
    """Refuses execution against production unless explicit --allow-prod flag is given."""
    if GENUDO_ENV == "prod" and not allow_prod_flag:
        print("\n" + "=" * 70, file=sys.stderr)
        print("CRITICAL SAFETY BLOCK: GENUDO_ENV is set to 'prod'!", file=sys.stderr)
        print("Running automated test simulations against production agents creates real leads,", file=sys.stderr)
        print("fires webhooks into live order sheets, and affects CRM conversions.", file=sys.stderr)
        print("To proceed, you must explicitly provide the '--allow-prod' command line flag.", file=sys.stderr)
        print("=" * 70 + "\n", file=sys.stderr)
        sys.exit(2)
