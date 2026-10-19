"""Accesso a Home Assistant e al Supervisor dall'interno dell'add-on.

Il Supervisor passa all'add-on la variabile SUPERVISOR_TOKEN, valida sia per l'API di
Home Assistant (http://supervisor/core/api) sia per quella del Supervisor (http://supervisor).
"""
import json
import os
import urllib.error
import urllib.request

HA_URL = os.environ.get("HA_URL", "http://supervisor/core/api").rstrip("/")
SUPERVISOR_URL = os.environ.get("SUPERVISOR_URL", "http://supervisor").rstrip("/")
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")


class HAError(Exception):
    pass


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise HAError(f"{url}: {e}") from e


def states():
    return _get(f"{HA_URL}/states")


def config():
    return _get(f"{HA_URL}/config")


def supervisor(path):
    """Restituisce il campo 'data' di una risposta del Supervisor, o None se non disponibile."""
    try:
        res = _get(f"{SUPERVISOR_URL}/{path.lstrip('/')}")
    except HAError:
        return None
    return res.get("data") if isinstance(res, dict) and res.get("result") == "ok" else None
