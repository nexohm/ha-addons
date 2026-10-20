"""Agente Assistenza: collega l'Home Assistant del cliente al server dell'installatore.

Tre attività in parallelo:
  - rapporti: battito periodico + diagnostica (se il cliente ha dato il consenso)
  - comandi: long-polling verso il server, esegue solo i comandi della lista chiusa
  - pannello: interfaccia per il cliente nella barra laterale di HA
"""
import json
import logging
import os
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

    # ---- utilità ----

    def wake(self):
        """Forza un rapporto immediato (es. dopo un cambio di consenso)."""
        self._wake.set()

    def ha_urls(self):
        """Indirizzi di Home Assistant impostati dal cliente (Impostazioni → Sistema → Rete).
        Il server li mostra all'installatore come pulsante "Apri Home Assistant"."""
        try:
            cfg = ha.config()
        except ha.HAError:
            return None
        self._ha_version = cfg.get("version") or self._ha_version
        return {"internal": cfg.get("internal_url"), "external": cfg.get("external_url")}

    def ha_version(self):
        if not self._ha_version:
            try:
                self._ha_version = ha.config().get("version")
            except ha.HAError:
                pass
        return self._ha_version

    def fresh_diagnostics(self):
        with self._diag_lock:
            diag = diagnostics.collect()
            self._last_diag_time = time.monotonic()
            self.state.update(last_diag=diag)
            return diag

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
            if self.state.consent_active() and due:
                try:
                    diag = self.fresh_diagnostics()
                except ha.HAError as e:
                    log.warning("Diagnostica non riuscita: %s", e)
            try:
                urls = self.ha_urls()
                self.link.report(self.ha_version(), diag, urls)
                self.state.update(connection="collegato", last_error=None, last_contact=time.time())
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
