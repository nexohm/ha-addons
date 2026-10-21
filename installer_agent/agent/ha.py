"""Accesso a Home Assistant e al Supervisor dall'interno dell'add-on.

Il Supervisor dà all'add-on una chiave (SUPERVISOR_TOKEN), valida sia per l'API di
Home Assistant (http://supervisor/core/api) sia per quella del Supervisor (http://supervisor).

Nelle immagini base di Home Assistant (s6-overlay) la chiave non sempre arriva come variabile
d'ambiente al programma: s6 la salva in /run/s6/container_environment. La cerchiamo in tutti
e due i posti, e anche con il vecchio nome HASSIO_TOKEN.
"""
import base64
import json
import os
import socket
import struct
import time
import urllib.error
import urllib.parse
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


def _post(url, body, timeout=15):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
                                          "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise HAError(f"{url}: {e}") from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise HAError(f"{url}: {e}") from e


def call_service(domain, service, data):
    return _post(f"{HA_URL}/services/{domain}/{service}", data)


# Servizi notify da non proporre al cliente: la campanella è già un'opzione a parte,
# send_message è il nuovo servizio "per entità" che richiede un target.
NOTIFY_SKIP = {"persistent_notification", "send_message"}


def notify_services():
    """Servizi notify configurati in Home Assistant (app sul telefono, Telegram, email...)."""
    for entry in _get(f"{HA_URL}/services"):
        if isinstance(entry, dict) and entry.get("domain") == "notify":
            return sorted(s for s in (entry.get("services") or {}) if s not in NOTIFY_SKIP)
    return []


def panel_path():
    """Percorso del pannello "Assistenza" dentro Home Assistant (per aprirlo toccando la notifica)."""
    info = supervisor("addons/self/info") or {}
    slug = info.get("slug")
    return f"/hassio/ingress/{slug}" if slug else None


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


# ---------------------------------------------------------------- websocket di Home Assistant
#
# Alcune informazioni esistono solo sull'API websocket, ad esempio gli indirizzi "calcolati"
# (rete locale in automatico, Home Assistant Cloud): sull'API REST restano vuoti.
# Client minimo, solo libreria standard: autenticazione, una richiesta, una risposta.

WS_URL = os.environ.get("HA_WS_URL") or (
    HA_URL.replace("https://", "wss://").replace("http://", "ws://").rsplit("/api", 1)[0] + "/websocket")


class _Conn:
    """Socket con i byte già ricevuti insieme all'handshake (HA può mandare subito il primo messaggio)."""

    def __init__(self, sock, pending=b""):
        self.sock, self.pending = sock, pending

    def recv(self, n):
        if self.pending:
            data, self.pending = self.pending[:n], self.pending[n:]
            return data
        return self.sock.recv(n)

    def sendall(self, data):
        self.sock.sendall(data)


def _ws_send(sock, data):
    payload = json.dumps(data).encode()
    header = bytes([0x81])  # FIN + testo
    n = len(payload)
    if n < 126:
        header += bytes([0x80 | n])
    elif n < 65536:
        header += bytes([0x80 | 126]) + struct.pack("!H", n)
    else:
        header += bytes([0x80 | 127]) + struct.pack("!Q", n)
    mask = os.urandom(4)
    sock.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise HAError("websocket chiuso da Home Assistant")
        buf += chunk
    return buf


def _ws_recv(sock):
    message = b""
    while True:
        b1, b2 = _recv_exact(sock, 2)
        opcode, length = b1 & 0x0F, b2 & 0x7F
        if length == 126:
            length = struct.unpack("!H", _recv_exact(sock, 2))[0]
        elif length == 127:
            length = struct.unpack("!Q", _recv_exact(sock, 8))[0]
        if length > 16 * 1024 * 1024:
            raise HAError("messaggio websocket troppo grande")
        mask = _recv_exact(sock, 4) if b2 & 0x80 else None
        data = _recv_exact(sock, length)
        if mask:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        if opcode == 0x8:
            raise HAError("websocket chiuso da Home Assistant")
        if opcode in (0x9, 0xA):  # ping/pong: ignorati
            continue
        message += data
        if b1 & 0x80:
            return json.loads(message.decode())


def ws_command(command, timeout=10, **params):
    """Esegue un comando websocket di Home Assistant e ne restituisce il risultato."""
    return ws_commands([(command, params)], timeout)[0]


def ws_commands(commands, timeout=10):
    """Più comandi websocket sulla stessa connessione: [(tipo, {parametri}), ...] -> [risultati]."""
    url = urllib.parse.urlsplit(WS_URL)
    port = url.port or (443 if url.scheme == "wss" else 80)
    path = url.path or "/"
    try:
        sock = socket.create_connection((url.hostname, port), timeout=timeout)
    except OSError as e:
        raise HAError(f"websocket non raggiungibile: {e}") from e
    try:
        if url.scheme == "wss":
            import ssl
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=url.hostname)
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {url.netloc}\r\nUpgrade: websocket\r\n"
                      f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
                      f"Authorization: Bearer {TOKEN}\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = sock.recv(1024)
            if not chunk:
                raise HAError("handshake websocket interrotto")
            head += chunk
            if len(head) > 16384:
                raise HAError("handshake websocket non valido")
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise HAError("handshake websocket rifiutato: " + head.split(b"\r\n", 1)[0].decode(errors="replace"))
        raw = sock
        sock = _Conn(raw, head.split(b"\r\n\r\n", 1)[1])
        msg = _ws_recv(sock)
        if msg.get("type") == "auth_required":
            _ws_send(sock, {"type": "auth", "access_token": TOKEN})
            msg = _ws_recv(sock)
            if msg.get("type") != "auth_ok":
                raise HAError("autenticazione websocket non riuscita")
        for i, (command, params) in enumerate(commands, 1):
            _ws_send(sock, {"id": i, "type": command, **(params or {})})
        results = {}
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(results) < len(commands):
            msg = _ws_recv(sock)
            mid = msg.get("id")
            if isinstance(mid, int) and 1 <= mid <= len(commands) and msg.get("type") == "result":
                if not msg.get("success"):
                    raise HAError(f"comando {commands[mid - 1][0]} non riuscito: {(msg.get('error') or {}).get('message')}")
                results[mid] = msg.get("result")
        if len(results) < len(commands):
            raise HAError("nessuna risposta ai comandi websocket")
        return [results[i] for i in range(1, len(commands) + 1)]
    except (OSError, ValueError) as e:
        raise HAError(f"websocket: {e}") from e
    finally:
        try:
            (sock.sock if isinstance(sock, _Conn) else sock).close()
        except OSError:
            pass


def labels():
    """Etichette definite in Home Assistant: {label_id: nome}."""
    result = ws_command("config/label_registry/list")
    return {l["label_id"]: l.get("name") or l["label_id"] for l in result or []
            if isinstance(l, dict) and isinstance(l.get("label_id"), str)}


def entity_labels():
    """Etichette di ogni entità, comprese quelle del dispositivo a cui appartiene: {entity_id: {label_id}}."""
    ents, devs = ws_commands([("config/entity_registry/list_for_display", {}), ("config/device_registry/list", {})], timeout=20)
    dev_labels = {d["id"]: set(d.get("labels") or []) for d in devs or [] if isinstance(d, dict) and d.get("id")}
    out = {}
    for e in (ents or {}).get("entities", []) if isinstance(ents, dict) else []:
        if isinstance(e, dict) and isinstance(e.get("ei"), str):
            out[e["ei"]] = set(e.get("lb") or []) | dev_labels.get(e.get("di"), set())
    return out


def _clean_url(value):
    return value.rstrip("/") if isinstance(value, str) and value.startswith(("http://", "https://")) else None


def network_urls():
    """Indirizzi di Home Assistant come li vede la schermata Impostazioni → Sistema → Rete.

    1. websocket "network/url": interno ed esterno anche se calcolati in automatico,
       più l'indirizzo di Home Assistant Cloud (Nabu Casa) se attivo;
    2. altrimenti la configurazione (indirizzi scritti a mano);
    3. per l'interno, in ultima istanza: IP del sistema + porta di Home Assistant.
    """
    internal = external = None
    try:
        res = ws_command("network/url") or {}
        internal = _clean_url(res.get("internal"))
        external = _clean_url(res.get("external")) or _clean_url(res.get("cloud"))
    except HAError:
        pass
    if not (internal and external):
        try:
            cfg = config()
            internal = internal or _clean_url(cfg.get("internal_url"))
            external = external or _clean_url(cfg.get("external_url"))
        except HAError:
            pass
    if not internal:
        core = supervisor("core/info") or {}
        net = supervisor("network/info") or {}
        for iface in net.get("interfaces") or []:
            addresses = ((iface.get("ipv4") or {}).get("address")) or []
            if iface.get("primary") and addresses:
                ip = addresses[0].split("/")[0]
                scheme = "https" if core.get("ssl") else "http"
                internal = f"{scheme}://{ip}:{core.get('port') or 8123}"
                break
    return {"internal": internal, "external": external}
