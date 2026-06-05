"""Hermes plugin adapter for ZAP command rewriting.

All rewrite logic lives in ZAP's Rust ``zap rewrite`` command; this module
only bridges Hermes ``pre_tool_call`` payloads to that command and fails open.
"""

import shutil
import subprocess
import sys


ACCEPTED_REWRITE_RETURN_CODES = {0, 3}
EXPECTED_PASSTHROUGH_RETURN_CODES = {1, 2}
_zap_available = None
_zap_missing_warned = False


def register(ctx):
    """Register the Hermes pre-tool callback."""
    if not _check_zap():
        return

    ctx.register_hook("pre_tool_call", _pre_tool_call)


def _check_zap():
    """Return whether the zap binary is in PATH, warning once when missing."""
    global _zap_available, _zap_missing_warned

    if _zap_available is None:
        _zap_available = shutil.which("zap") is not None

    if not _zap_available and not _zap_missing_warned:
        _warn("zap binary not found in PATH; Hermes hook not registered")
        _zap_missing_warned = True

    return _zap_available


def _pre_tool_call(tool_name=None, args=None, **_kwargs):
    """Rewrite mutable Hermes terminal command args when ZAP provides a change."""
    try:
        if tool_name != "terminal" or not isinstance(args, dict):
            return

        command = args.get("command")
        if not isinstance(command, str) or not command.strip():
            return

        try:
            result = subprocess.run(
                ["zap", "rewrite", command],
                shell=False,
                timeout=2,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired:
            _warn("zap rewrite timed out")
            return

        if result.returncode not in ACCEPTED_REWRITE_RETURN_CODES:
            if result.returncode not in EXPECTED_PASSTHROUGH_RETURN_CODES:
                details = f"zap rewrite failed with exit {result.returncode}"
                stderr = result.stderr.strip()
                if stderr:
                    details = f"{details}: {stderr}"
                _warn(details)
            return

        rewritten = result.stdout.strip()
        if rewritten and rewritten != command:
            args["command"] = rewritten
    except Exception as e:
        _warn(str(e))
        return


def _warn(message):
    print(f"zap: hermes plugin warning: {message}", file=sys.stderr)
