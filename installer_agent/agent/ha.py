"""Accesso a Home Assistant e al Supervisor dall'interno dell'add-on.

Il Supervisor dà all'add-on una chiave (SUPERVISOR_TOKEN), valida sia per l'API di
Home Assistant (http://supervisor/core/api) sia per quella del Supervisor (http://supervisor).

Nelle immagini base di Home Assistant (s6-overlay) la chiave non sempre arriva come variabile
d'ambiente al programma: s6 la salva in /run/s6/container_environment. La cerchiamo in tutti
e due i posti, e anche con il vecchio nome HASSIO_TOKEN.
"""
import json
import os
import urllib.error
import urllib.request

HA_URL = os.environ.get("HA_URL", "http://supervisor/core/api").rstrip("/")
SUPERVISOR_URL = os.environ.get("SUPERVISOR_URL", "http://supervisor").rstrip("/")
CONTAINER_ENV = os.environ.get("S6_CONTAINER_ENV", "/run/s6/container_environment")


def _find_token():
    for name in ("SUPERVISOR_TOKEN", "HASSIO_TOKEN"):
        if os.environ.get(name):
            return os.environ[name].strip(), f"variabile {name}"
    for name in ("SUPERVISOR_TOKEN", "HASSIO_TOKEN"):
        try:
            with open(os.path.join(CONTAINER_ENV, name)) as f:
                value = f.read().strip()
            if value:
                return value, f"file s6 {name}"
        except OSError:
            pass
    return "", None


TOKEN, TOKEN_SOURCE = _find_token()


class HAError(Exception):
    pass


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise HAError("Home Assistant ha rifiutato l'accesso dell'add-on (401): "
                          + ("chiave del Supervisor mancante" if not TOKEN else "permessi API non concessi")) from e
        raise HAError(f"{url}: {e}") from e
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
