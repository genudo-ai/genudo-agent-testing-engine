"""Self-check for reusing a client folder's .mcp.json token. Run: python3 tests/test_config.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from config import token_from_mcp_json  # noqa: E402


def _write(path, auth, url="https://api.genudo.ai/mcp"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"mcpServers": {"genudo": {"type": "http", "url": url,
                                              "headers": {"Authorization": auth}}}}, f)


def test_token_found_in_parent_folder():
    with tempfile.TemporaryDirectory() as client:
        engine = os.path.join(client, "genudo-agent-testing-engine")
        os.makedirs(engine)
        _write(os.path.join(client, ".mcp.json"), "Bearer abc123")
        tok, url, src = token_from_mcp_json(engine)
        assert (tok, url) == ("abc123", "https://api.genudo.ai/mcp"), (tok, url)
        assert src == os.path.join(client, ".mcp.json")


def test_env_var_reference_is_expanded_or_skipped():
    with tempfile.TemporaryDirectory() as client:
        _write(os.path.join(client, ".mcp.json"), "Bearer ${GENUDO_TOKEN_TEST_CLIENT}")
        os.environ.pop("GENUDO_TOKEN_TEST_CLIENT", None)
        assert token_from_mcp_json(client)[0] == ""  # unresolved var is not a token
        os.environ["GENUDO_TOKEN_TEST_CLIENT"] = "xyz789"
        try:
            assert token_from_mcp_json(client)[0] == "xyz789"
        finally:
            del os.environ["GENUDO_TOKEN_TEST_CLIENT"]


def test_oauth_only_config_has_no_token():
    with tempfile.TemporaryDirectory() as client:
        with open(os.path.join(client, ".mcp.json"), "w", encoding="utf-8") as f:
            json.dump({"mcpServers": {"genudo": {"type": "http", "url": "https://api.genudo.ai/mcp"}}}, f)
        assert token_from_mcp_json(client)[0] == ""



def test_untrusted_host_or_foreign_env_var_is_refused():
    with tempfile.TemporaryDirectory() as client:
        _write(os.path.join(client, ".mcp.json"), "Bearer abc123", url="https://evil.example.com/mcp")
        assert token_from_mcp_json(client)[0] == ""  # token never paired with a non-genudo host
        _write(os.path.join(client, ".mcp.json"), "Bearer abc123", url="http://api.genudo.ai/mcp")
        assert token_from_mcp_json(client)[0] == ""  # plain http refused
        _write(os.path.join(client, ".mcp.json"), "Bearer abc123", url="https://genudo.ai.evil.com/mcp")
        assert token_from_mcp_json(client)[0] == ""  # suffix trick refused
        os.environ["SOME_OTHER_SECRET"] = "s3cret"
        try:
            _write(os.path.join(client, ".mcp.json"), "Bearer ${SOME_OTHER_SECRET}")
            assert token_from_mcp_json(client)[0] == ""  # only ${GENUDO_*} is expanded
        finally:
            del os.environ["SOME_OTHER_SECRET"]

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"{len(tests)} tests passed")
