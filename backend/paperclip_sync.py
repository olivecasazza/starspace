"""Paperclip -> Starspace agent state sync.

Polls the paperclip control-plane board API and mirrors every paperclip
agent into the office agents-state as an approved, paperclip-sourced
visitor. Pure stdlib; started from app.py's __main__ block only when
PAPERCLIP_API_KEY is set.

Env:
    PAPERCLIP_API_URL       base URL (default http://paperclip.apps.svc.cluster.local:3100)
    PAPERCLIP_API_KEY       board API key (bearer). Sync disabled when unset.
    PAPERCLIP_SYNC_INTERVAL poll interval seconds (default 20)

Auth notes: board API keys are validated by the paperclip server without
any Host-header routing; requests are read-only GETs.
"""

import json
import os
import threading
import urllib.request
from datetime import datetime

DEFAULT_BASE_URL = "http://paperclip.apps.svc.cluster.local:3100"
DEFAULT_INTERVAL = 20

# Exposed for /health: last sync outcome.
status = {
    "enabled": False,
    "lastOkAt": None,
    "lastError": None,
    "agentCount": 0,
}

_lock = threading.Lock()


def _fetch_json(url, token, host_header=None, timeout=8):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    # Paperclip validates the Host header against its allowed-hosts list
    # (PAPERCLIP_PUBLIC_URL + localhost); the in-cluster service DNS is
    # NOT on it, so cluster-internal callers must pin the public host —
    # same PAPERCLIP_HOST_HEADER convention as the paperclip-deploy
    # reconcile job.
    if host_header:
        headers["Host"] = host_header
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}


def _map_state(agent, runtime):
    """Map a paperclip agent + runtime-state onto an office state.

    Signals: agent.status (idle|error|paused|...), runtime.lastRunStatus
    (running|succeeded|failed), runtime.lastError. runtime.sessionId is
    NOT a liveness signal - it persists after a run completes.
    Granular writing/researching/syncing is not derivable from the board
    API, so active runs collapse to "executing".
    """
    runtime = runtime or {}
    last_run = (runtime.get("lastRunStatus") or "").lower()
    last_error = runtime.get("lastError") or ""
    if agent.get("status") == "error" or last_run == "failed" or last_error:
        detail = (last_error or "agent reported error status")[:120]
        return "error", detail
    if last_run == "running":
        return "executing", ""
    if agent.get("status") == "paused":
        return "idle", "paused"
    return "idle", ""


def _collect(base_url, token, host_header=None):
    """Fetch companies -> agents -> runtime-state. Raises on any failure so
    a partial fetch never wipes the office snapshot."""
    entries = []
    companies = _fetch_json(f"{base_url}/api/companies", token, host_header)
    if not isinstance(companies, list):
        raise ValueError(f"unexpected /api/companies payload: {type(companies).__name__}")
    for company in companies:
        cid = company.get("id")
        if not cid:
            continue
        agents = _fetch_json(f"{base_url}/api/companies/{cid}/agents", token, host_header)
        if not isinstance(agents, list):
            raise ValueError(f"unexpected agents payload for company {cid}")
        for agent in agents:
            aid = agent.get("id")
            if not aid:
                continue
            try:
                runtime = _fetch_json(f"{base_url}/api/agents/{aid}/runtime-state", token, host_header)
            except Exception:
                runtime = None  # runtime-state is optional enrichment
            state, detail = _map_state(agent, runtime)
            title = agent.get("title") or agent.get("role") or ""
            now = datetime.now().isoformat()
            entries.append(
                {
                    "agentId": aid,
                    "name": agent.get("name") or "agent",
                    "isMain": False,
                    "state": state,
                    "detail": detail or title,
                    "updated_at": now,
                    "area": None,  # filled by caller's state_to_area
                    "_state": state,
                    "company": company.get("name"),
                    "source": "paperclip",
                    "joinKey": None,
                    "authStatus": "approved",
                    "authExpiresAt": None,
                    "lastPushAt": now,
                }
            )
    return entries


def sync_once(load_agents, save_agents, state_to_area, base_url, token, host_header=None):
    """One merge pass. On success replaces all paperclip-sourced agents and
    preserves the main Star plus any manually joined agents verbatim."""
    entries = _collect(base_url, token, host_header)
    for e in entries:
        e["area"] = state_to_area(e["_state"])
        del e["_state"]
    with _lock:
        agents = load_agents()
        kept = [a for a in agents if a.get("isMain") or a.get("source") != "paperclip"]
        save_agents(kept + entries)
    status["lastOkAt"] = datetime.now().isoformat()
    status["lastError"] = None
    status["agentCount"] = len(entries)
    return len(entries)


def _loop(load_agents, save_agents, state_to_area, base_url, token, host_header, interval):
    while True:
        try:
            sync_once(load_agents, save_agents, state_to_area, base_url, token, host_header)
        except Exception as e:  # keep last snapshot on transient failures
            status["lastError"] = str(e)[:200]
        # Python has no interruptible sleep primitive we need here; the
        # thread is a daemon and dies with the process.
        threading.Event().wait(interval)


def start_background_sync(load_agents, save_agents, state_to_area):
    """Start the poller if configured. Returns True when started."""
    token = (os.environ.get("PAPERCLIP_API_KEY") or "").strip()
    if not token:
        return False
    # Paperclip's allowed-hosts check rejects the in-cluster service DNS;
    # default to the public host (same convention as PAPERCLIP_HOST_HEADER
    # in the paperclip-deploy reconcile job).
    host_header = (os.environ.get("PAPERCLIP_HOST_HEADER") or "paperclip.casazza.io").strip()
    try:
        interval = max(5, int(os.environ.get("PAPERCLIP_SYNC_INTERVAL", str(DEFAULT_INTERVAL))))
    except ValueError:
        interval = DEFAULT_INTERVAL
    status["enabled"] = True
    t = threading.Thread(
        target=_loop,
        args=(load_agents, save_agents, state_to_area, base_url, token, host_header, interval),
        daemon=True,
        name="paperclip-sync",
    )
    t.start()
    return True
