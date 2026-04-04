"""Starspace plugin for Hermes Agent.

Pushes agent state transitions to a Star Office UI (Starspace) dashboard
via its /set_state HTTP endpoint. Maps hermes lifecycle hooks to the
pixel-office states: idle, writing, researching, executing, error.

Install:
    hermes plugins install olivecasazza/starspace

Configure:
    STARSPACE_URL=http://starspace.apps.svc.cluster.local:19000
"""

import logging
import os
import threading
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = logging.getLogger(__name__)

STARSPACE_URL = os.environ.get("STARSPACE_URL", "http://localhost:19000")

# Map hermes tool names to starspace states for more granular status
_TOOL_STATE_MAP = {
    "bash": "executing",
    "terminal": "executing",
    "execute": "executing",
    "run_command": "executing",
    "shell": "executing",
    "search": "researching",
    "web_search": "researching",
    "web_fetch": "researching",
    "read_file": "researching",
    "grep": "researching",
    "glob": "researching",
    "write_file": "writing",
    "edit_file": "writing",
    "create_file": "writing",
    "git_commit": "syncing",
    "git_push": "syncing",
}


def _push_state(state: str, detail: str = "") -> None:
    """POST state to Starspace in a background thread (non-blocking)."""
    import json

    def _do_push():
        try:
            url = f"{STARSPACE_URL}/set_state"
            payload = json.dumps({"state": state, "detail": detail}).encode()
            req = Request(url, data=payload, headers={"Content-Type": "application/json"})
            urlopen(req, timeout=3)
        except (URLError, OSError) as e:
            logger.debug("starspace push failed: %s", e)

    threading.Thread(target=_do_push, daemon=True).start()


def register(ctx) -> None:
    """Register lifecycle hooks with hermes plugin system."""

    @ctx.hook("on_session_start")
    def on_session_start(**kwargs):
        _push_state("idle", "Session started")

    @ctx.hook("on_session_end")
    def on_session_end(**kwargs):
        _push_state("idle", "Session ended")

    @ctx.hook("pre_llm_call")
    def pre_llm_call(**kwargs):
        _push_state("researching", "Thinking...")

    @ctx.hook("post_llm_call")
    def post_llm_call(**kwargs):
        _push_state("replying", "Responding")

    @ctx.hook("pre_tool_call")
    def pre_tool_call(**kwargs):
        tool_name = kwargs.get("tool_name", "")
        tool_input = kwargs.get("tool_input", {})
        state = _TOOL_STATE_MAP.get(tool_name, "executing")
        detail = tool_name
        if isinstance(tool_input, dict):
            # Add a short description from the tool input
            cmd = tool_input.get("command", tool_input.get("query", ""))
            if cmd:
                detail = f"{tool_name}: {str(cmd)[:80]}"
        _push_state(state, detail)

    @ctx.hook("post_tool_call")
    def post_tool_call(**kwargs):
        error = kwargs.get("error")
        if error:
            _push_state("error", str(error)[:120])
        else:
            _push_state("idle", "Ready")

    logger.info("starspace plugin registered (url=%s)", STARSPACE_URL)
