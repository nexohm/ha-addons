"""Backup e aggiornamenti avviati dall'installatore dalla sua dashboard.

Possono durare molti minuti (un backup completo, l'aggiornamento di Home Assistant che lo riavvia),
quindi il comando risponde subito con "avviato" e il lavoro continua in un thread. L'avanzamento
viaggia al server con i rapporti ("jobs"). Regole:
  - serve l'accesso remoto concesso dal cliente (controllato da Agent.execute);
  - un'operazione alla volta;
  - prima di ogni aggiornamento viene fatto un backup completo; se il backup non riesce,
    l'aggiornamento non parte;
  - il cliente riceve una notifica all'inizio dell'aggiornamento e alla fine di ogni operazione.
"""
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone

from . import ha
from .admin import person

log = logging.getLogger("agent.jobs")

KEEP = 10                       # operazioni recenti tenute nello stato e mandate al server
BACKUP_TIMEOUT = 3600           # un backup completo di una casa grande può richiedere parecchi minuti
INSTALL_TIMEOUT = 1800          # attesa massima della fine di un aggiornamento
POLL = int(os.environ.get("JOBS_POLL", "15"))   # ogni quanto si ricontrolla l'entità durante l'aggiornamento
ENTITY = re.compile(r"update\.[a-z0-9_]{1,120}")


def _iso(ts=None):
    return datetime.fromtimestamp(ts or time.time(), timezone.utc).isoformat(timespec="seconds")


class Jobs:
    def __init__(self, agent):
        self.agent = agent
        self.state = agent.state
        self._lock = threading.Lock()

    # ---- stato ----

    def list(self):
        return [j for j in self.state.get("jobs") or [] if isinstance(j, dict)]

    def _save(self, job):
        with self._lock:
            jobs = [j for j in self.list() if j.get("id") != job["id"]] + [job]
            self.state.update(jobs=jobs[-KEEP:])

    def status(self):
        """Riassunto per il server: niente dati sensibili, solo cosa, stato e messaggio."""
        keys = ("id", "kind", "title", "entity_id", "from", "to", "status", "message", "by", "started_at", "finished_at")
        return [{k: j.get(k) for k in keys} for j in self.list()]

    def running(self):
        return next((j for j in self.list() if j.get("status") == "in_corso"), None)

    # ---- avvio (dal comando del server) ----

    def start(self, cmd_id, kind, args):
        """Restituisce (ok, risultato, errore) come Agent.execute. Un comando rispedito dal server
        (risposta persa per strada) non fa partire una seconda operazione."""
        same = next((j for j in self.list() if j.get("id") == cmd_id), None)
        if same:
            return True, {"started": True, "job": same["id"], "status": same["status"]}, None
        busy = self.running()
        if busy:
            return False, None, f"c'è già un'operazione in corso: {busy.get('title')}"
        by = person(args.get("by"))
        job = {"id": cmd_id, "kind": kind, "status": "in_corso", "message": None, "by": by,
               "started_at": _iso(), "finished_at": None, "entity_id": None, "from": None, "to": None}
        if kind == "backup":
            job["title"] = "Backup completo"
        else:
            eid = args.get("entity_id")
            if not isinstance(eid, str) or not ENTITY.fullmatch(eid):
                return False, None, "aggiornamento non valido"
            try:
                st = ha.state(eid)
            except ha.HAError as e:
                return False, None, f"Home Assistant non risponde: {e}"
            if not st or st.get("state") != "on":
                return False, None, "nessun aggiornamento disponibile per questa voce"
            attrs = st.get("attributes") or {}
            if not int(attrs.get("supported_features") or 0) & 1:
                return False, None, "questo aggiornamento non si può installare da remoto"
            job.update(entity_id=eid, title=str(attrs.get("title") or attrs.get("friendly_name") or eid)[:80],
                       **{"from": str(attrs.get("installed_version") or "")[:40], "to": str(attrs.get("latest_version") or "")[:40]})
        self._save(job)
        threading.Thread(target=self._run, args=(job,), daemon=True, name=f"job-{cmd_id}").start()
        return True, {"started": True, "job": cmd_id}, None

    # ---- esecuzione ----

    def _company(self):
        return self.agent._plain(self.state.get("server_name") or "Assistenza", 60)

    def _who(self, job):
        by = self.agent._plain(job.get("by"), 60) if job.get("by") else None
        return f"{by} di {self._company()}" if by else self._company()

    def _finish(self, job, ok, message):
        job.update(status="completato" if ok else "errore", message=message, finished_at=_iso())
        self._save(job)
        title = self.agent._plain(job.get("title"), 80)
        if job["kind"] == "backup":
            text = "Backup completo creato." if ok else f"Backup non riuscito: {self.agent._plain(message, 200)}"
        else:
            text = (f"{title} aggiornato alla versione {self.agent._plain(job.get('to'), 40)}." if ok
                    else f"Aggiornamento di {title} non riuscito: {self.agent._plain(message, 200)}")
        self.agent.notify_client(f"{self._company()}: {'operazione completata' if ok else 'operazione non riuscita'}",
                                 text, f"operazione_{job['id']}")
        self.agent.send_diagnostics_soon()   # l'installatore vede subito backup e aggiornamenti aggiornati

    def _backup(self, job, reason):
        stamp = datetime.now(ha.local_tz()).strftime("%d/%m/%Y %H:%M")
        name = f"Assistenza {stamp} - {reason}"[:80]
        job["message"] = "backup completo in corso"
        self._save(job)
        data = ha.supervisor_post("backups/new/full", {"name": name}, timeout=BACKUP_TIMEOUT) or {}
        return data.get("slug")

    def _run(self, job):
        try:
            if job["kind"] == "backup":
                self._backup(job, "richiesto dall'installatore")
                self._finish(job, True, "backup completato")
                return
            self.agent.notify_client(
                f"{self._company()}: aggiornamento in corso",
                f"{self._who(job)} sta aggiornando {self.agent._plain(job['title'], 80)} "
                f"({self.agent._plain(job.get('from'), 40)} → {self.agent._plain(job.get('to'), 40)}). "
                "Prima viene fatto un backup completo; Home Assistant potrebbe riavviarsi.", f"operazione_{job['id']}")
            try:
                self._backup(job, f"prima di aggiornare {job['title']}")
            except ha.HAError as e:
                self._finish(job, False, f"backup non riuscito, aggiornamento non eseguito ({e})")
                return
            job["message"] = "installazione in corso"
            self._save(job)
            try:
                ha.call_service("update", "install", {"entity_id": job["entity_id"]}, timeout=INSTALL_TIMEOUT)
            except ha.HAError as e:
                # Home Assistant, sistema operativo e Supervisor si riavviano durante l'installazione:
                # la connessione cade anche quando va tutto bene. Decide lo stato dell'entità.
                log.info("Installazione di %s: connessione interrotta (%s), controllo l'esito", job["entity_id"], e)
            ok, message = self._wait_installed(job)
            self._finish(job, ok, message)
        except Exception as e:  # noqa: BLE001 — un'operazione non deve mai fermare l'agente
            log.exception("Operazione %s non riuscita", job.get("id"))
            self._finish(job, False, str(e)[:200])

    def _installed(self, job):
        """True se l'aggiornamento risulta installato, False se è ancora disponibile, None se non si sa."""
        try:
            st = ha.state(job["entity_id"])
        except ha.HAError:
            return None
        if st is None:
            return None
        attrs = st.get("attributes") or {}
        if st.get("state") == "off" or (job.get("to") and attrs.get("installed_version") == job["to"]):
            return True
        if attrs.get("in_progress"):
            return None
        return False if st.get("state") == "on" else None

    def _wait_installed(self, job):
        deadline = time.monotonic() + INSTALL_TIMEOUT
        while time.monotonic() < deadline:
            done = self._installed(job)
            if done:
                return True, "aggiornamento installato"
            if done is False and time.monotonic() > deadline - INSTALL_TIMEOUT + 2 * POLL:
                # ancora disponibile e non in corso dopo un po': l'installazione non è partita o è fallita
                return False, "dopo l'installazione l'aggiornamento risulta ancora da fare"
            time.sleep(POLL)
        return False, "l'aggiornamento non si è concluso entro 30 minuti"

    # ---- dopo un riavvio dell'add-on ----

    def recover(self):
        """Operazioni rimaste "in corso" (l'add-on si è riavviato, per esempio aggiornando il sistema
        operativo o l'add-on stesso): si guarda com'è finita."""
        for job in self.list():
            if job.get("status") != "in_corso":
                continue
            if job.get("kind") == "update" and self._installed(job):
                job.update(status="completato", message="aggiornamento installato", finished_at=_iso())
            else:
                job.update(status="errore", message="operazione interrotta dal riavvio dell'add-on", finished_at=_iso())
            self._save(job)
