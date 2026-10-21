"""Accesso amministratore temporaneo dell'installatore all'Home Assistant del cliente.

Regole (vedi anche il pannello, scheda Impianto):
  - il PERMESSO lo dà solo il cliente, dal pannello, scegliendo la durata (anche senza scadenza);
    l'installatore può soltanto chiederlo;
  - l'UTENTE in Home Assistant viene creato solo quando l'installatore preme «Mostra password», e ogni
    volta da zero: password nuova e sessioni precedenti chiuse (cancellando l'utente HA chiude anche le
    sue sessioni). La password non viene mai salvata dall'agente;
  - la scadenza la controlla l'agente, non il server: alla scadenza l'utente viene cancellato anche se
    il server è spento o irraggiungibile, e anche dopo un riavvio;
  - senza scadenza: se per 30 giorni nessuno chiede la password l'utente viene cancellato (il permesso
    resta), e ogni 30 giorni il cliente riceve un promemoria per chiudere l'accesso.
"""
import logging
import secrets
import string
import threading
import time
from datetime import datetime, timezone

from . import ha

log = logging.getLogger("agent.admin")

DURATIONS = {"1h": 1, "4h": 4, "24h": 24, "7g": 24 * 7, "sempre": None}
DURATION_LABELS = [("1h", "1 ora"), ("4h", "4 ore"), ("24h", "24 ore"), ("7g", "7 giorni"), ("sempre", "Senza scadenza")]
IDLE_DAYS = 30        # senza scadenza: utente cancellato dopo 30 giorni senza richieste di password
REMINDER_DAYS = 30    # senza scadenza: promemoria al cliente ogni 30 giorni
REQUEST_MAX_AGE = 24 * 3600  # una richiesta dell'installatore vale 24 ore

DEFAULT = {"granted": False, "until": None, "granted_at": None, "user_id": None, "username": None,
           "last_reveal": None, "last_reminder": None, "request": None, "request_notified": None, "declined": None,
           "request_by": None, "reveal_by": None}


def person(value):
    """Nome del tecnico che arriva dal server: solo testo semplice, una riga, al massimo 60 caratteri."""
    if not isinstance(value, str):
        return None
    value = " ".join("".join(ch for ch in value if ch.isprintable()).split())[:60]
    return value or None


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds") if ts else None


def _password():
    # 24 caratteri da 62 simboli: ~143 bit, senza simboli che si confondono quando si copia
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(24))


class AdminAccess:
    def __init__(self, agent):
        self.agent = agent
        self.state = agent.state
        self._lock = threading.RLock()

    # ---- stato ----

    def get(self):
        return {**DEFAULT, **(self.state.get("admin") or {})}

    def _save(self, **changes):
        with self._lock:
            self.state.update(admin={**self.get(), **changes})

    def active(self):
        a = self.get()
        return bool(a["granted"]) and not (a["until"] and time.time() >= a["until"])

    def status(self):
        """Quello che il server deve sapere (mai la password)."""
        a = self.get()
        return {"active": self.active(), "permanent": self.active() and a["until"] is None,
                "until": _iso(a["until"]) if self.active() else None,
                "username": a["username"] if a["user_id"] else None,
                "last_reveal": _iso(a["last_reveal"]),
                "declined": a["declined"]}

    def _name(self):
        return self.state.get("server_name") or "l'installatore"

    # ---- azioni del cliente (pannello) ----

    def grant(self, duration):
        if duration not in DURATIONS:
            raise ValueError("durata non valida")
        hours = DURATIONS[duration]
        now = time.time()
        self._save(granted=True, until=now + hours * 3600 if hours else None, granted_at=now,
                   last_reminder=now, request=None, declined=None)
        self.agent.wake()
        return hours

    def decline(self):
        a = self.get()
        self._save(request=None, declined=a["request"])
        self.agent.wake()

    def close(self, reason="cliente", by=None):
        """Chiude il permesso e cancella l'utente (se c'è). by: tecnico che l'ha chiuso, se noto."""
        with self._lock:
            a = self.get()
            was = a["granted"] or a["user_id"]
            # prima si toglie il permesso, poi si cancella l'utente: se HA non risponde,
            # la cancellazione viene ritentata dal controllo periodico
            self._save(granted=False, until=None, granted_at=None, last_reveal=None)
            try:
                self._delete_user()
            except ha.HAError as e:
                log.warning("Utente amministratore non ancora cancellato, riprovo: %s", e)
        if was and reason != "cliente":
            msgs = {"scaduto": "è scaduto ed è stato chiuso automaticamente",
                    "installatore": (f"è stato chiuso da {self.agent._plain(person(by), 60)}" if person(by) else "è stato chiuso dall'installatore"),
                    "scollegato": "è stato chiuso perché l'impianto non è più collegato all'assistenza",
                    "sospeso": "è stato chiuso perché l'assistenza è sospesa"}
            self.agent.notify_client(f"{self._plain_name()}: accesso amministratore chiuso",
                                     f"L'accesso amministratore di {self._plain_name()} {msgs.get(reason, 'è stato chiuso')}.",
                                     "admin")
        self.agent.wake()
        return bool(was)

    def _plain_name(self):
        return self.agent._plain(self._name(), 60)

    def _plain_who(self, by):
        """«Mario Rossi di Rossi Impianti», oppure solo l'azienda se il tecnico non è noto."""
        if by and by.casefold() != self._name().casefold():
            return f"{self.agent._plain(by, 60)} di {self._plain_name()}"
        return self._plain_name()

    # ---- richieste dall'installatore (dal rapporto col server) ----

    def on_server_request(self, requested_at, requested_by=None):
        """requested_at: data della richiesta dell'installatore, oppure None.
        requested_by: nome del tecnico che l'ha chiesta (server più vecchi non lo mandano)."""
        a = self.get()
        if not isinstance(requested_at, str) or len(requested_at) > 40:
            requested_at = None
        if requested_at == a["declined"]:
            return  # già rifiutata dal cliente
        by = person(requested_by) if requested_at else None
        if requested_at != a["request"] or by != a["request_by"]:
            self._save(request=requested_at, request_by=by)
        if requested_at and not self.active() and a["request_notified"] != requested_at:
            self._save(request_notified=requested_at)
            self.agent.notify_client(f"{self._plain_name()}: richiesta di accesso amministratore",
                                     f"{self._plain_who(by)} chiede l'accesso amministratore al tuo Home Assistant. "
                                     "Apri il pannello Assistenza, scheda Impianto, per consentirlo o rifiutarlo.",
                                     "admin")

    # ---- comandi dell'installatore ----

    def reveal(self, by=None):
        """Crea l'utente da zero (password nuova, sessioni vecchie chiuse) e restituisce le credenziali."""
        if not self.active():
            raise PermissionError("il cliente non ha concesso l'accesso amministratore")
        with self._lock:
            self._delete_user()
            username = "assistenza_" + secrets.token_hex(3)
            password = _password()
            by = person(by)
            label = f"{by} · {self._name()}" if by and by.casefold() != self._name().casefold() else self._name()
            result = ha.ws_command("config/auth/create", name=f"{label} (assistenza)"[:60],
                                   group_ids=["system-admin"], local_only=False)
            user_id = ((result or {}).get("user") or {}).get("id")
            if not isinstance(user_id, str):
                raise ha.HAError("Home Assistant non ha restituito l'utente creato")
            # salvato subito: se il passo dopo fallisce, l'utente va comunque cancellato
            self._save(user_id=user_id, username=None)
            try:
                ha.ws_command("config/auth_provider/homeassistant/create", user_id=user_id,
                              username=username, password=password)
            except ha.HAError:
                self._delete_user()
                raise
            self._save(username=username, last_reveal=time.time(), reveal_by=by)
        log.info("Utente amministratore %s creato per l'installatore", username)
        self.agent.notify_client(f"{self._plain_name()}: accesso amministratore in uso",
                                 f"{self._plain_who(by)} ha appena aperto una sessione da amministratore nel tuo "
                                 "Home Assistant. Puoi chiuderla quando vuoi dal pannello Assistenza.", "admin")
        return {"username": username, "password": password}

    def drop_user(self):
        """Cancella l'utente HA lasciando il permesso del cliente (usato all'arresto dell'add-on)."""
        with self._lock:
            self._delete_user()

    # ---- controllo periodico (anche senza server) ----

    def _delete_user(self):
        a = self.get()
        if not a["user_id"]:
            return
        try:
            ha.ws_command("config/auth/delete", user_id=a["user_id"])
        except ha.HAError as e:
            if "not found" not in str(e).lower() and "non trovato" not in str(e).lower():
                raise
        log.info("Utente amministratore %s cancellato", a["username"])
        self._save(user_id=None, username=None)

    def tick(self):
        now = time.time()
        a = self.get()
        try:
            if a["granted"] and a["until"] and now >= a["until"]:
                self.close("scaduto")
                return
            if a["granted"] and not self.agent.paired():
                self.close("scollegato")
                return
            if a["granted"] and self.state.get("connection") == "sospeso":
                self.close("sospeso")
                return
            if not a["granted"] and a["user_id"]:
                self._delete_user()  # cancellazione rimasta in sospeso (es. HA non rispondeva)
                return
            if a["granted"] and a["until"] is None:
                if a["user_id"] and a["last_reveal"] and now - a["last_reveal"] > IDLE_DAYS * 86400:
                    log.info("Accesso amministratore senza scadenza inutilizzato da %s giorni: utente cancellato", IDLE_DAYS)
                    self._delete_user()
                if now - (a["last_reminder"] or a["granted_at"] or now) > REMINDER_DAYS * 86400:
                    self._save(last_reminder=now)
                    self.agent.notify_client(f"{self._plain_name()}: accesso amministratore ancora attivo",
                                             f"{self._plain_name()} ha ancora l'accesso amministratore senza scadenza al tuo "
                                             "Home Assistant. Se non serve più, chiudilo dal pannello Assistenza, scheda Impianto.",
                                             "admin")
            if a["request"] and a["request"] != a["declined"]:
                try:
                    age = now - datetime.fromisoformat(a["request"].replace("Z", "+00:00")).timestamp()
                except ValueError:
                    age = REQUEST_MAX_AGE + 1
                if age > REQUEST_MAX_AGE:
                    self._save(request=None)
        except ha.HAError as e:
            log.warning("Accesso amministratore: operazione rimandata (%s)", e)

    def loop(self):
        while True:
            try:
                self.tick()
            except Exception:  # noqa: BLE001 — il controllo della scadenza non deve mai fermarsi
                log.exception("Errore nel controllo dell'accesso amministratore")
            time.sleep(20)
