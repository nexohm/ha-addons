"""Collegamento con il server dell'installatore e stato persistente dell'agente."""
import json
import logging
import os
import threading
import urllib.error
import urllib.request

AGENT_VERSION = "0.1.0"
PROTOCOL = 1
DATA_DIR = os.environ.get("DATA_DIR", "/data")
STATE_PATH = os.path.join(DATA_DIR, "state.json")

log = logging.getLogger("agent")


class State:
    """Stato salvato in /data/state.json: sopravvive a riavvii e aggiornamenti dell'add-on."""

    DEFAULTS = {
        "server_url": None, "plant_id": None, "token": None, "server_name": None, "brand_color": None, "paired_code": None,
        "consent": True, "connection": "non_configurato", "last_error": None, "last_contact": None,
        "last_diag": None,
    }

    def __init__(self):
        self._lock = threading.Lock()
        self._data = dict(self.DEFAULTS)
        try:
            with open(STATE_PATH) as f:
                self._data.update(json.load(f))
        except (OSError, ValueError):
            pass

    def get(self, key):
        with self._lock:
            return self._data.get(key)

    def update(self, **values):
        with self._lock:
            self._data.update(values)
            tmp = STATE_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self._data, f)
            os.replace(tmp, STATE_PATH)

    def snapshot(self):
        with self._lock:
            return dict(self._data)


class ServerError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class Link:
    def __init__(self, state: State):
        self.state = state

    def _request(self, method, path, body=None, timeout=30, auth=True, base=None):
        base = (base or self.state.get("server_url") or "").rstrip("/")
        headers = {"Content-Type": "application/json", "X-Agent-Protocol": str(PROTOCOL),
                   "X-Agent-Version": AGENT_VERSION, "Accept": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {self.state.get('token')}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                message = json.loads(e.read().decode()).get("error", e.reason)
            except ValueError:
                message = str(e.reason)
            raise ServerError(e.code, message) from e
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise ServerError(0, f"server non raggiungibile: {getattr(e, 'reason', e)}") from e

    # ---- protocollo v1 (vedi protocol/PROTOCOL.md) ----

    def pair(self, server_url, code, ha_version, location_name):
        res = self._request("POST", "/api/agent/pair", {
            "code": code, "ha_version": ha_version, "agent_version": AGENT_VERSION, "location_name": location_name,
        }, auth=False, base=server_url)
        self.state.update(server_url=server_url.rstrip("/"), plant_id=res["plant_id"], token=res["token"],
                          server_name=res.get("server_name"), brand_color=res.get("brand_color"), paired_code=code, connection="collegato",
                          last_error=None)
        return res

    def report(self, ha_version=None, diagnostics=None):
        body = {"consent": bool(self.state.get("consent")), "ha_version": ha_version}
        if diagnostics is not None:
            body["diagnostics"] = diagnostics
        res = self._request("POST", "/api/agent/report", body)
        branding = {k: res[k] for k in ("server_name", "brand_color") if res.get(k) and res[k] != self.state.get(k)}
        if branding:
            self.state.update(**branding)
        return res

    def poll_commands(self, wait=25):
        return self._request("GET", f"/api/agent/commands?wait={wait}", timeout=wait + 15).get("commands", [])

    def command_result(self, cid, ok, result=None, error=None):
        body = {"ok": ok, "result": result} if ok else {"ok": False, "error": error}
        return self._request("POST", f"/api/agent/commands/{cid}/result", body)

    def tickets(self):
        return self._request("GET", "/api/agent/tickets").get("tickets", [])

    def open_ticket(self, title, description, contact, diagnostics):
        return self._request("POST", "/api/agent/tickets", {
            "title": title, "description": description, "contact": contact, "diagnostics": diagnostics})

    def reply_ticket(self, tid, text):
        return self._request("POST", f"/api/agent/tickets/{tid}/messages", {"text": text})
