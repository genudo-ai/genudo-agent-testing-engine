"""
Configuration and Environment Management for GenuDo Testing Engine.
"""

import json
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

def token_from_mcp_json(start):
    """Reuse the `genudo` server's bearer token from the nearest .mcp.json at or above `start`.

    Client folders made by `loredex workspace` (or `claude mcp add --header`) already hold a
    per-client token there, so an engine cloned inside one needs no token of its own.
    Returns (token, mcp_url, path) or ("", "", "").
    """
    d = os.path.abspath(start)
    while True:
        p = os.path.join(d, ".mcp.json")
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    srv = json.load(f)["mcpServers"]["genudo"]
                auth = os.path.expandvars(srv.get("headers", {}).get("Authorization", ""))
                tok = auth.removeprefix("Bearer ").strip()
                if tok and "$" not in tok:
                    return tok, srv.get("url", ""), p
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                pass
        parent = os.path.dirname(d)
        if parent == d:
            return "", "", ""
        d = parent

load_dotenv()

if os.environ.get("GENUDO_TOKEN", "").startswith("your_"):  # untouched .env.example placeholder
    del os.environ["GENUDO_TOKEN"]
if not os.environ.get("GENUDO_TOKEN"):
    _tok, _url, _src = token_from_mcp_json(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _tok:
        os.environ["GENUDO_TOKEN"] = _tok  # set in env so judge redaction / env scrubbing see it
        if _url and not os.environ.get("GENUDO_BASE"):
            os.environ["GENUDO_BASE"] = _url.rstrip("/").removesuffix("/mcp")
        print(f"[config] Using the GenuDo token from {_src}", file=sys.stderr)

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
