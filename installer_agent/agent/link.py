"""Collegamento con il server dell'installatore e stato persistente dell'agente."""
import ipaddress
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
import urllib.error
import urllib.parse
import urllib.request

AGENT_VERSION = "0.1.8-dev5"
PROTOCOL = 1
DATA_DIR = os.environ.get("DATA_DIR", "/data")
STATE_PATH = os.path.join(DATA_DIR, "state.json")

log = logging.getLogger("agent")

MAX_RESPONSE = 2 * 1024 * 1024  # nessuna risposta legittima del server si avvicina a 2 MB
LOCAL_SUFFIXES = (".local", ".lan", ".home", ".home.arpa", ".internal", ".localdomain")


def insecure_reason(url):
    """Motivo per cui l'indirizzo del server non è accettabile, oppure None se va bene.

    Il token dell'impianto e la diagnostica viaggiano a ogni richiesta: su internet devono
    essere cifrati (https). L'http resta ammesso solo per server nella rete di casa."""
    parts = urllib.parse.urlsplit(url or "")
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host:
        return "indirizzo del server non valido (es. https://assistenza.tuaditta.it)"
    if parts.scheme == "https":
        return None
    if host == "localhost" or "." not in host or host.endswith(LOCAL_SUFFIXES):
        return None
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return None
    except ValueError:
        pass
    return "per sicurezza l'indirizzo del server deve iniziare con https:// (http è ammesso solo in rete locale)"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Niente reindirizzamenti: urllib li seguirebbe portandosi dietro il token, anche verso
    un altro sito. Se il server risponde con un redirect lo segnaliamo come errore."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, f"reindirizzamento verso {newurl}", headers, fp)


_opener = urllib.request.build_opener(_NoRedirect)


class State:
    """Stato salvato in /data/state.json: sopravvive a riavvii e aggiornamenti dell'add-on."""

    DEFAULTS = {
        "server_url": None, "plant_id": None, "token": None, "server_name": None, "brand_color": None, "paired_code": None,
        "consent": True, "consent_until": None, "connection": "non_configurato", "last_error": None, "last_contact": None,
        "last_diag": None,
        # scelte del cliente nel pannello
        "excluded": [], "only_labels": [], "flagged": [], "admin": None,
        "ticket_retention": {"days": None, "max_closed": None},
        "notify": {"ha": True, "services": []},
        "tickets_seen": None, "tickets_updated": None,
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

    def consent_active(self):
        """Consenso del cliente, tenendo conto della scadenza scelta: se è scaduta lo spegne."""
        with self._lock:
            consent, until = self._data.get("consent"), self._data.get("consent_until")
        if consent and until and time.time() >= until:
            log.info("Accesso remoto scaduto: sospeso automaticamente")
            self.update(consent=False, consent_until=None)
            return False
        return bool(consent)

    def set_consent(self, enabled, hours=None):
        """hours=None: senza scadenza."""
        until = time.time() + hours * 3600 if enabled and hours else None
        self.update(consent=bool(enabled), consent_until=until)

    def snapshot(self):
        with self._lock:
            return dict(self._data)


class ServerError(Exception):
    def __init__(self, status, message, from_server=True):
        super().__init__(message)
        self.status = status
        # False quando la risposta non arriva dal server Nexohm ma da qualcosa in mezzo
        # (Cloudflare, un proxy, un firewall): in quel caso un 401 non vuol dire "revocato".
        self.from_server = from_server


class Link:
    def __init__(self, state: State):
        self.state = state

    def _request(self, method, path, body=None, timeout=30, auth=True, base=None):
        base = (base or self.state.get("server_url") or "").rstrip("/")
        reason = insecure_reason(base)
        if reason:
            raise ServerError(0, reason, from_server=False)
        # Un'identità propria: filtri anti-bot (es. Cloudflare) bloccano spesso "Python-urllib".
        headers = {"User-Agent": f"NexohmAgent/{AGENT_VERSION} (Home Assistant add-on)",
                   "Content-Type": "application/json", "X-Agent-Protocol": str(PROTOCOL),
                   "X-Agent-Version": AGENT_VERSION, "Accept": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {self.state.get('token')}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
        try:
            with _opener.open(req, timeout=timeout) as r:
                raw = r.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise ServerError(0, "risposta del server troppo grande", from_server=False)
                data = json.loads(raw.decode() or "{}")
                if not isinstance(data, dict):
                    raise ServerError(0, "risposta del server non valida", from_server=False)
                return data
        except urllib.error.HTTPError as e:
            if 300 <= e.code < 400:
                raise ServerError(e.code, f"il server ha risposto con un {e.reason}: usa direttamente "
                                          "l'indirizzo finale (con https://) nella configurazione", from_server=False) from e
            body = (e.read(64 * 1024) if e.fp else b"").decode(errors="replace")
            try:
                message = str(json.loads(body).get("error") or e.reason)[:300]
                from_server = True
            except (ValueError, AttributeError):
                from_server = False
                if e.code == 403 or "cloudflare" in body.lower():
                    message = (f"bloccato prima di raggiungere il server ({e.code} {e.reason}): "
                               "controlla le regole di sicurezza di Cloudflare o del proxy")
                else:
                    message = f"risposta inattesa dal proxy davanti al server ({e.code} {e.reason})"
            raise ServerError(e.code, message, from_server) from e
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise ServerError(0, f"server non raggiungibile: {getattr(e, 'reason', e)}") from e

    # ---- protocollo v1 (vedi protocol/PROTOCOL.md) ----

    def pair(self, server_url, code, ha_version, location_name):
        res = self._request("POST", "/api/agent/pair", {
            "code": code, "ha_version": ha_version, "agent_version": AGENT_VERSION, "location_name": location_name,
        }, auth=False, base=server_url)
        if not isinstance(res.get("token"), str) or not res["token"]:
            raise ServerError(0, "risposta di abbinamento non valida", from_server=False)
        self.state.update(server_url=server_url.rstrip("/"), plant_id=res.get("plant_id"), token=res["token"],
                          server_name=res.get("server_name"), brand_color=res.get("brand_color"), paired_code=code, connection="collegato",
                          last_error=None)
        return res

    def report(self, ha_version=None, diagnostics=None, ha_urls=None, admin=None):
        consent = self.state.consent_active()
        until = self.state.get("consent_until") if consent else None
        body = {"consent": consent, "ha_version": ha_version,
                "consent_until": datetime.fromtimestamp(until, timezone.utc).isoformat(timespec="seconds") if until else None}
        if diagnostics is not None:
            body["diagnostics"] = diagnostics
        if ha_urls is not None:
            body["ha_urls"] = ha_urls
        if admin is not None:
            body["admin"] = admin
        res = self._request("POST", "/api/agent/report", body)
        branding = {k: str(res[k])[:100] for k in ("server_name", "brand_color")
                    if isinstance(res.get(k), str) and res[k] and res[k] != self.state.get(k)}
        if branding:
            self.state.update(**branding)
        return res

    def poll_commands(self, wait=25):
        cmds = self._request("GET", f"/api/agent/commands?wait={wait}", timeout=wait + 15).get("commands")
        return [c for c in cmds if isinstance(c, dict) and isinstance(c.get("id"), int)] if isinstance(cmds, list) else []

    def command_result(self, cid, ok, result=None, error=None):
        body = {"ok": ok, "result": result} if ok else {"ok": False, "error": error}
        return self._request("POST", f"/api/agent/commands/{cid}/result", body)

    def tickets(self):
        tickets = self._request("GET", "/api/agent/tickets").get("tickets")
        return tickets if isinstance(tickets, list) else []

    def open_ticket(self, title, description, contact, diagnostics):
        return self._request("POST", "/api/agent/tickets", {
            "title": title, "description": description, "contact": contact, "diagnostics": diagnostics})

    def reply_ticket(self, tid, text):
        return self._request("POST", f"/api/agent/tickets/{tid}/messages", {"text": text})
