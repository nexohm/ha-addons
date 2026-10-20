"""Agente Assistenza: collega l'Home Assistant del cliente al server dell'installatore.

Tre attività in parallelo:
  - rapporti: battito periodico + diagnostica (se il cliente ha dato il consenso)
  - comandi: long-polling verso il server, esegue solo i comandi della lista chiusa
  - pannello: interfaccia per il cliente nella barra laterale di HA
"""
import json
import logging
import os
import re
import sys
import threading
import time

from . import diagnostics, ha
from .link import AGENT_VERSION, DATA_DIR, Link, ServerError, State
from .panel import Panel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout)
log = logging.getLogger("agent")

OPTIONS_PATH = os.path.join(DATA_DIR, "options.json")


def load_options():
    try:
        with open(OPTIONS_PATH) as f:
            opts = json.load(f)
    except (OSError, ValueError):
        opts = {}
    return {
        "server_url": (opts.get("server_url") or "").strip().rstrip("/"),
        "pair_code": (opts.get("pair_code") or "").strip().upper(),
        "heartbeat_seconds": max(15, int(opts.get("heartbeat_seconds") or 60)),
        "diagnostics_minutes": max(1, int(opts.get("diagnostics_minutes") or 15)),
    }


class Agent:
    def __init__(self):
        self.options = load_options()
        self.state = State()
        self.link = Link(self.state)
        self._wake = threading.Event()
        self._diag_lock = threading.Lock()
        self._last_diag_time = 0.0
        self._ha_version = None
        self._urls, self._urls_at = None, 0.0
        self._send_diag_now = False
        self._last_ticket_check = 0.0

    # ---- utilità ----

    def wake(self):
        """Forza un rapporto immediato (es. dopo un cambio di consenso)."""
        self._wake.set()

    def ha_urls(self):
        """Indirizzi di Home Assistant impostati dal cliente (Impostazioni → Sistema → Rete).
        Il server li mostra all'installatore come pulsante "Apri Home Assistant"."""
        # Gli indirizzi cambiano di rado: li ricalcoliamo ogni 10 minuti.
        now = time.monotonic()
        if self._urls is None or now - self._urls_at > 600:
            self._urls, self._urls_at = ha.network_urls(), now
        return self._urls

    def ha_version(self):
        if not self._ha_version:
            try:
                self._ha_version = ha.config().get("version")
            except ha.HAError:
                pass
        return self._ha_version

    def fresh_diagnostics(self):
        with self._diag_lock:
            only = self.state.get("only_labels") or []
            # Se il filtro per etichette non si può applicare, meglio nessun controllo che mostrare
            # all'installatore entità che il cliente ha escluso: ha.HAError ferma questo giro.
            labels_of = ha.entity_labels() if only else None
            diag = diagnostics.collect(self.state.get("excluded") or [], only, labels_of)
            flagged = diag.pop("_flagged", [])   # solo per il pannello del cliente, non va al server
            self._last_diag_time = time.monotonic()
            self.state.update(last_diag=diag, flagged=flagged)
            return diag

    def send_diagnostics_soon(self):
        """Dopo una modifica del cliente (es. entità escluse): rifà il controllo e lo invia subito."""
        self._send_diag_now = True
        self.wake()

    # ---- notifiche al cliente sulle risposte dell'installatore ----

    @staticmethod
    def _plain(text, limit=300):
        """Testo che arriva dal server, ripulito per le notifiche di Home Assistant (che interpretano
        il Markdown): niente link, immagini o formattazione decise dal server."""
        text = re.sub(r"<[^>]*>", "", str(text or ""))
        text = re.sub(r"([\\`*_{}\[\]()#+!|>~])", r"\\\1", text)
        text = " ".join(text.split())
        return text[:limit] + ("…" if len(text) > limit else "")

    def notify_client(self, title, message, tag):
        settings = self.state.get("notify") or {}
        sent = 0
        if settings.get("ha", True):
            try:
                ha.call_service("persistent_notification", "create",
                                {"title": title, "message": message, "notification_id": f"assistenza_{tag}"})
                sent += 1
            except ha.HAError as e:
                log.warning("Notifica in Home Assistant non riuscita: %s", e)
        services = [s for s in settings.get("services") or [] if re.fullmatch(r"[a-z0-9_]+", s)]
        if services:
            path = ha.panel_path()
            for svc in services:
                data = {"title": title, "message": message}
                if path:
                    data["data"] = {"url": path, "clickAction": path, "tag": f"assistenza_{tag}"}
                try:
                    ha.call_service("notify", svc, data)
                    sent += 1
                except ha.HAError as e:
                    log.warning("Notifica con notify.%s non riuscita: %s", svc, e)
        return sent

    def check_ticket_updates(self, tickets_updated=None, server_tells=False):
        """Rilegge i ticket se il server dice che sono cambiati (o ogni 5 minuti con server vecchi)
        e avvisa il cliente delle risposte e dei cambi di stato fatti dall'installatore."""
        now = time.monotonic()
        if server_tells:
            if tickets_updated == self.state.get("tickets_updated") and self.state.get("tickets_seen") is not None:
                return
        elif now - self._last_ticket_check < 300:
            return
        self._last_ticket_check = now
        try:
            tickets = self.link.tickets()
        except ServerError as e:
            log.warning("Ticket non letti: %s", e)
            return
        seen = self.state.get("tickets_seen")
        new_seen = {}
        name = self.state.get("server_name") or "Assistenza"
        labels = {"aperto": "riaperta", "in_lavorazione": "presa in carico", "chiuso": "chiusa"}
        for t in tickets:
            if not isinstance(t, dict) or not isinstance(t.get("id"), int):
                continue
            msgs = [m for m in (t.get("messages") if isinstance(t.get("messages"), list) else []) if isinstance(m, dict)]
            inst = [m for m in msgs if m.get("author_type") == "installatore"]
            status = t.get("status") if t.get("status") in labels else None
            key = str(t["id"])
            new_seen[key] = {"status": status, "inst": len(inst)}
            if seen is None:
                continue  # primo controllo dopo l'avvio: registriamo lo stato senza avvisare
            # Richiesta mai vista (appena aperta dal cliente): avvisiamo solo se l'installatore
            # ha già risposto prima che l'agente la rileggesse.
            prev = seen.get(key) or {"status": status, "inst": 0}
            title = self._plain(t.get("title"), 80)
            if len(inst) > prev.get("inst", 0):
                self.notify_client(f"{self._plain(name, 60)}: nuova risposta",
                                   f"«{title}»: {self._plain(inst[-1].get('text'))}", f"ticket_{key}")
            elif status and status != prev.get("status"):
                self.notify_client(f"{self._plain(name, 60)}: richiesta {labels[status]}",
                                   f"La tua richiesta «{title}» è stata {labels[status]}.", f"ticket_{key}")
        if seen is not None:
            new_seen = {**{k: v for k, v in seen.items() if k not in new_seen}, **new_seen}
        # teniamo solo i ticket recenti per non far crescere lo stato all'infinito
        self.state.update(tickets_seen=dict(list(new_seen.items())[-200:]), tickets_updated=tickets_updated)

    def paired(self):
        return bool(self.state.get("token")) and self.state.get("connection") not in ("revocato", "aggiornare")

    def _handle_server_error(self, e: ServerError):
        if not e.from_server:
            self.state.update(connection="errore", last_error=str(e))
        elif e.status == 401:
            log.error("Il server ha rifiutato il token: abbinamento revocato.")
            self.state.update(connection="revocato", token=None,
                              last_error="L'installatore ha revocato il collegamento. Serve un nuovo codice di abbinamento.")
        elif e.status == 426:
            self.state.update(connection="aggiornare", last_error=str(e))
        else:
            self.state.update(connection="errore", last_error=str(e))

    # ---- abbinamento ----

    def ensure_paired(self):
        opts = self.options
        s = self.state.snapshot()
        same_server = s.get("server_url") == opts["server_url"]
        new_code = opts["pair_code"] and opts["pair_code"] != s.get("paired_code")
        if s.get("token") and same_server and not new_code:
            return True
        if s.get("connection") == "revocato" and not new_code:
            return False  # serve un nuovo codice: inutile riprovare con quello vecchio
        if not opts["server_url"] or not opts["pair_code"]:
            self.state.update(connection="non_configurato", last_error=None)
            return False
        try:
            res = self.link.pair(opts["server_url"], opts["pair_code"], self.ha_version(), self._location_name())
            log.info("Abbinato a «%s» come impianto %s", res.get("server_name"), res.get("plant_id"))
            self._last_diag_time = 0
            return True
        except ServerError as e:
            log.error("Abbinamento non riuscito: %s", e)
            self.state.update(connection="errore", last_error=f"Abbinamento non riuscito: {e}")
            return False

    def _location_name(self):
        try:
            return ha.config().get("location_name")
        except ha.HAError:
            return None

    # ---- ciclo dei rapporti ----

    def report_loop(self):
        failures = 0
        while True:
            if not self.paired():
                time.sleep(5)
                continue
            diag = None
            due = time.monotonic() - self._last_diag_time >= self.options["diagnostics_minutes"] * 60
            if self.state.consent_active() and (due or self._send_diag_now):
                try:
                    diag = self.fresh_diagnostics()
                except ha.HAError as e:
                    log.warning("Diagnostica non riuscita: %s", e)
            self._send_diag_now = False
            try:
                urls = self.ha_urls()
                res = self.link.report(self.ha_version(), diag, urls) or {}
                self.state.update(connection="collegato", last_error=None, last_contact=time.time())
                self.check_ticket_updates(res.get("tickets_updated"), server_tells="tickets_updated" in res)
                failures = 0
                wait = self.options["heartbeat_seconds"]
            except ServerError as e:
                self._handle_server_error(e)
                failures += 1
                wait = min(300, 5 * 2 ** failures)
                log.warning("Rapporto non inviato (%s), riprovo tra %ss", e, wait)
            self._wake.wait(wait)
            self._wake.clear()

    # ---- ciclo dei comandi ----

    COMMANDS = {"ping", "run_diagnostics"}

    def execute(self, cmd):
        name = cmd.get("name")
        if name not in self.COMMANDS:
            return False, None, f"comando «{name}» non permesso da questo agente"
        if name == "ping":
            return True, {"agent_version": AGENT_VERSION, "ha_version": self.ha_version(), "time": time.time()}, None
        if not self.state.consent_active():
            return False, None, "accesso remoto sospeso dal cliente"
        if name == "run_diagnostics":
            return True, self.fresh_diagnostics(), None
        return False, None, "comando non gestito"

    def command_loop(self):
        failures = 0
        while True:
            if not self.paired():
                time.sleep(5)
                continue
            try:
                for cmd in self.link.poll_commands():
                    log.info("Comando ricevuto: %s (#%s)", cmd.get("name"), cmd.get("id"))
                    try:
                        ok, result, error = self.execute(cmd)
                    except Exception as e:  # noqa: BLE001
                        log.exception("Errore eseguendo il comando")
                        ok, result, error = False, None, str(e)
                    self.link.command_result(cmd["id"], ok, result, error)
                failures = 0
            except ServerError as e:
                self._handle_server_error(e)
                failures += 1
                wait = min(300, 5 * 2 ** failures)
                log.warning("Attesa comandi interrotta (%s), riprovo tra %ss", e, wait)
                time.sleep(wait)

    # ---- avvio ----

    def run(self):
        log.info("Agente Assistenza %s in avvio", AGENT_VERSION)
        if ha.TOKEN:
            log.info("Chiave del Supervisor trovata (%s)", ha.TOKEN_SOURCE)
        else:
            log.error("Chiave del Supervisor NON trovata: la diagnostica non potrà leggere Home Assistant")
        Panel(self, int(os.environ.get("PANEL_PORT", "8099"))).start()
        threading.Thread(target=self.report_loop, daemon=True, name="report").start()
        threading.Thread(target=self.command_loop, daemon=True, name="commands").start()
        while True:
            self.ensure_paired()
            time.sleep(60 if self.paired() else 30)


if __name__ == "__main__":
    Agent().run()
