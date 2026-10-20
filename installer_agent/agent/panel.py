"""Pannello "Assistenza" mostrato al cliente nella barra laterale di Home Assistant (ingress).

Tutti i link sono relativi: l'ingress di HA serve la pagina sotto un percorso tipo
/api/hassio_ingress/<token>/ e i link assoluti non funzionerebbero.
"""
import html
import re
import logging
import os
import secrets
import threading
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import ha
from .link import ServerError

log = logging.getLogger("agent.panel")

# Il Supervisor inoltra le richieste ingress solo da questo indirizzo.
INGRESS_IP = "172.30.32.2"
ALLOWED_IPS = {INGRESS_IP} | set(filter(None, os.environ.get("PANEL_ALLOW_IPS", "").split(",")))

STATUS_LABELS = {"ok": "Tutto regolare", "attenzione": "Da controllare", "critico": "Problemi da risolvere"}
TICKET_LABELS = {"aperto": "Aperta", "in_lavorazione": "In lavorazione", "chiuso": "Chiusa"}
CONNECTION_LABELS = {
    "collegato": ("Collegato", "ok"),
    "non_configurato": ("Da configurare", "off"),
    "errore": ("Non raggiungibile", "bad"),
    "revocato": ("Collegamento revocato", "bad"),
    "aggiornare": ("Aggiornare l'add-on", "bad"),
}

CSS = """
:root{--bg:var(--primary-background-color,#f4f5f2);--panel:#fff;--ink:#1c1f1e;--muted:#646b68;--line:#e1e4df;
--brand:#0f766e;--ok:#15803d;--okb:#e7f5ec;--warn:#a16207;--warnb:#fdf3dc;--bad:#b91c1c;--badb:#fbe9e9;--off:#52525b;--offb:#ececee;
font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color-scheme:light dark}
@media(prefers-color-scheme:dark){:root{--bg:#131615;--panel:#1b1f1e;--ink:#e8ebe9;--muted:#9aa29e;--line:#2c3230;
--okb:#12301f;--warnb:#352a0c;--badb:#3a1515;--offb:#2a2a2e;--ok:#4ade80;--warn:#facc15;--bad:#f87171;--off:#a1a1aa}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-size:15px;line-height:1.5}
main{max-width:860px;margin:0 auto;padding:24px 16px 48px}h1{font-size:1.4rem;margin:0}h2{font-size:1.02rem;margin:0 0 12px}
.muted{color:var(--muted)}.small{font-size:.85rem}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px;margin-top:16px}
.head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap}
.badge{display:inline-flex;align-items:center;gap:6px;font-size:.8rem;font-weight:600;padding:2px 9px;border-radius:999px}
.badge:before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}
.ok{color:var(--ok);background:var(--okb)}.attenzione,.in_lavorazione{color:var(--warn);background:var(--warnb)}
.critico,.bad,.aperto{color:var(--bad);background:var(--badb)}.off{color:var(--off);background:var(--offb)}.chiuso{color:var(--ok);background:var(--okb)}
label{display:block;font-weight:600;font-size:.88rem;margin:12px 0 5px}
input,textarea,select{width:100%;font:inherit;color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:9px 11px}
textarea{min-height:100px;resize:vertical}
.btn{font:inherit;font-weight:600;border:1px solid transparent;border-radius:8px;padding:8px 14px;cursor:pointer;background:var(--brand);color:#fff}
.btn.ghost{background:transparent;color:var(--ink);border-color:var(--line)}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.msg{border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin-top:8px}.msg.installatore{background:color-mix(in srgb,var(--brand) 9%,var(--panel))}
.msg p{margin:0;white-space:pre-wrap}.meta{color:var(--muted);font-size:.8rem}
details{border-top:1px solid var(--line);padding:12px 0}details:first-of-type{border-top:0}summary{cursor:pointer}
ul{margin:6px 0 0;padding-left:20px}
.toast{position:fixed;left:50%;bottom:20px;z-index:9;transform:translateX(-50%);display:flex;align-items:center;gap:12px;
max-width:min(520px,calc(100vw - 32px));background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:12px 16px 12px 12px;
box-shadow:0 12px 32px rgba(0,0,0,.2);font-weight:600;animation:tin .35s cubic-bezier(.2,.9,.3,1.2) both,tout .45s ease-in 4.6s forwards}
.toast.err{animation:tin .35s cubic-bezier(.2,.9,.3,1.2) both,tshake .4s ease .75s,tout .45s ease-in 9s forwards}
.toast svg{width:32px;height:32px;flex:0 0 32px}.toast .ring{fill:none;stroke-width:4;stroke-dasharray:145;stroke-dashoffset:145;animation:tdraw .5s ease-out .1s forwards}
.toast .mark{fill:none;stroke-width:5;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:48;stroke-dashoffset:48;animation:tdraw .35s ease-out .55s forwards}
.toast.ok .ring,.toast.ok .mark{stroke:var(--ok)}.toast.err .ring,.toast.err .mark{stroke:var(--bad)}
@keyframes tin{from{opacity:0;transform:translate(-50%,24px) scale(.96)}to{opacity:1;transform:translate(-50%,0)}}
@keyframes tout{to{opacity:0;transform:translate(-50%,16px);visibility:hidden}}@keyframes tdraw{to{stroke-dashoffset:0}}
@keyframes tshake{0%,100%{transform:translateX(-50%)}20%,60%{transform:translateX(calc(-50% - 7px))}40%,80%{transform:translateX(calc(-50% + 7px))}}
@media(prefers-reduced-motion:reduce){.toast,.toast.err{animation:tout .3s ease-in 6s forwards}.toast .ring,.toast .mark{animation:none;stroke-dashoffset:0}}
.list{list-style:none;padding:0;margin:8px 0 0}.list li{display:flex;align-items:center;gap:10px;padding:8px 0;border-top:1px solid var(--line)}
.list li:first-child{border-top:0}.list .grow{flex:1;min-width:0}.list code{font-size:.8rem;color:var(--muted);word-break:break-all}
.btn.small{padding:4px 10px;font-size:.85rem}.check{display:flex;align-items:center;gap:8px;font-weight:400;margin:8px 0}.check input{width:auto}
"""


# Il pannello gira nella stessa origine di Home Assistant (ingress): un testo malevolo che
# riuscisse a diventare codice avrebbe accesso a tutta la casa. Per questo, oltre a fare
# l'escape di ogni dato, la CSP vieta qualsiasi script: il pannello non ne usa.
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
                               "frame-ancestors 'self'; base-uri 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
MAX_FORM = 64 * 1024

# Entità da non controllare: dominio.nome, con * per indicarne più di una (es. sensor.robot_*)
ENTITY_PATTERN = re.compile(r"[a-z0-9_*]{1,60}\.[a-z0-9_*]{1,100}")
MAX_EXCLUDED = 200
# Richieste chiuse da mostrare (la cronologia completa resta all'installatore)
RETENTION_DAYS = {"7": "7 giorni", "30": "30 giorni", "90": "90 giorni"}
RETENTION_KEEP = {"3": "3", "5": "5", "10": "10", "20": "20"}

# Durate tra cui il cliente sceglie quando attiva l'accesso remoto (ore; None = senza scadenza)
DURATIONS = {"1h": 1, "4h": 4, "24h": 24, "7g": 24 * 7, "sempre": None}
DURATION_LABELS = [("1h", "1 ora"), ("4h", "4 ore"), ("24h", "24 ore"), ("7g", "7 giorni"), ("sempre", "Senza scadenza")]


def fmt_epoch(ts):
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%d/%m/%Y alle %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return "—"


def esc(value):
    return html.escape(str(value if value is not None else ""))


def fmt(ts):
    try:
        return datetime.fromisoformat(ts).astimezone().strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return "—"


def filter_tickets(tickets, retention, now=None):
    """Richieste da mostrare al cliente: tutte quelle aperte, e le chiuse entro i limiti scelti.
    Restituisce (visibili, quante chiuse sono nascoste)."""
    retention = retention or {}
    days, keep = retention.get("days"), retention.get("max_closed")
    now = now or datetime.now().astimezone()
    visible, closed = [], []
    for t in tickets:
        if isinstance(t, dict) and t.get("status") == "chiuso":
            closed.append(t)
        else:
            visible.append(t)
    def ts(t):
        try:
            return datetime.fromisoformat(t.get("updated_at")).astimezone()
        except (TypeError, ValueError):
            return now
    closed.sort(key=ts, reverse=True)
    shown = [t for t in closed if not days or (now - ts(t)).days < days]
    if keep:
        shown = shown[:keep]
    hidden = len(closed) - len(shown)
    visible_ids = {id(t) for t in visible + shown}
    return [t for t in tickets if id(t) in visible_ids], hidden


class Panel:
    def __init__(self, agent, port=8099):
        self.agent = agent
        self.port = port
        self.flash = None
        # Token anti-CSRF: ogni modulo lo porta con sé; un altro sito non lo conosce e non può
        # inviare moduli al pannello (per esempio per riattivare l'accesso remoto).
        self.csrf = secrets.token_urlsafe(24)

    def _hidden(self):
        return f'<input type="hidden" name="csrf" value="{self.csrf}">'

    def start(self):
        panel = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _allowed(self):
                if self.client_address[0] in ALLOWED_IPS:
                    return True
                self.send_error(403)
                return False

            def _security_headers(self):
                for k, v in SECURITY_HEADERS.items():
                    self.send_header(k, v)

            def do_GET(self):
                if self._allowed():
                    try:
                        body = panel.page().encode()
                    except Exception:  # noqa: BLE001 — il pannello non deve mai cadere
                        log.exception("errore nel pannello")
                        body = b"<!doctype html><meta charset=utf-8><p>Errore nel pannello: riprova tra poco.</p>"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self._security_headers()
                    self.end_headers()
                    self.wfile.write(body)

            def do_POST(self):
                if not self._allowed():
                    return
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    length = -1
                if length < 0 or length > MAX_FORM:
                    self.send_error(400 if length < 0 else 413)
                    return
                raw = self.rfile.read(length).decode(errors="replace")
                form = {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}
                form_lists = urllib.parse.parse_qs(raw)  # campi ripetuti (caselle di spunta)
                if not secrets.compare_digest(form.get("csrf", ""), panel.csrf):
                    panel.flash = ("Pagina scaduta: riprova.", True)
                else:
                    result = panel.handle(self.path.rsplit("/", 1)[-1], form, form_lists)
                    panel.flash = result if isinstance(result, tuple) or result is None else (result, False)
                # Torna alla pagina principale con un percorso relativo (compatibile con l'ingress).
                self.send_response(303)
                self.send_header("Location", "./")
                self._security_headers()
                self.end_headers()

        server = ThreadingHTTPServer(("0.0.0.0", self.port), Handler)
        threading.Thread(target=server.serve_forever, daemon=True, name="panel").start()
        log.info("Pannello in ascolto sulla porta %s", self.port)
        return server

    # ---- azioni ----

    def handle(self, action, form, lists=None):
        agent, state = self.agent, self.agent.state
        lists = lists or {}
        try:
            if action == "escludi":
                pattern = form.get("entity", "").strip().lower()
                if not ENTITY_PATTERN.fullmatch(pattern):
                    return ("Nome non valido: usa il formato dominio.nome, ad esempio sensor.telefono_batteria "
                            "(con * per indicarne più di una).", True)
                excluded = list(state.get("excluded") or [])
                if pattern in excluded:
                    return f"{pattern} era già esclusa."
                if len(excluded) >= MAX_EXCLUDED:
                    return (f"Puoi escludere al massimo {MAX_EXCLUDED} entità.", True)
                state.update(excluded=excluded + [pattern])
                self._refresh_diagnostics()
                return f"{pattern} non verrà più controllata dall'installatore."
            if action == "includi":
                pattern = form.get("entity", "")
                state.update(excluded=[p for p in state.get("excluded") or [] if p != pattern])
                self._refresh_diagnostics()
                return f"{pattern} viene di nuovo controllata."
            if action == "richieste":
                days = form.get("days", "")
                keep = form.get("max_closed", "")
                state.update(ticket_retention={"days": int(days) if days in RETENTION_DAYS else None,
                                               "max_closed": int(keep) if keep in RETENTION_KEEP else None})
                return "Preferenze della lista salvate."
            if action == "notifiche":
                available = set(self._notify_services())
                chosen = [s for s in lists.get("service", []) if s in available]
                state.update(notify={"ha": form.get("ha") == "1", "services": chosen})
                if form.get("prova") == "1":
                    sent = agent.notify_client(f"{state.get('server_name') or 'Assistenza'}: prova",
                                               "Le notifiche dell'assistenza funzionano.", "prova")
                    return ("Notifica di prova inviata." if sent else
                            ("Nessuna notifica inviata: scegli almeno un canale.", True))
                return "Preferenze delle notifiche salvate."
            if action == "consenso":
                enabled = form.get("enabled") == "1"
                hours = DURATIONS.get(form.get("durata", "sempre"))
                state.set_consent(enabled, hours)
                agent.wake()
                if not enabled:
                    return "Accesso remoto sospeso: l'installatore vede solo se l'impianto è online."
                if hours:
                    return f"Accesso remoto attivato fino al {fmt_epoch(state.get('consent_until'))}."
                return "Accesso remoto attivato, senza scadenza."
            if action == "ticket":
                title = form.get("title", "").strip()
                if not title:
                    return ("Scrivi almeno un titolo per la richiesta.", True)
                diag = agent.fresh_diagnostics() if state.consent_active() else None
                agent.link.open_ticket(title, form.get("description", "").strip(), form.get("contact", "").strip(), diag)
                return "Richiesta inviata. Riceverai la risposta qui."
            if action == "rispondi":
                text = form.get("text", "").strip()
                if text:
                    agent.link.reply_ticket(int(form.get("tid", 0)), text)
                    return "Messaggio inviato."
                return None
            if action == "diagnostica":
                agent.fresh_diagnostics()
                return "Controllo completato."
        except ServerError as e:
            return (f"Impossibile contattare l'assistenza: {e}", True)
        except Exception as e:  # noqa: BLE001 — il pannello non deve mai cadere
            log.exception("errore nel pannello")
            return (f"Errore: {e}", True)
        return None

    def _refresh_diagnostics(self):
        try:
            self.agent.fresh_diagnostics()
        except Exception:  # noqa: BLE001 — se HA non risponde, il controllo partirà al prossimo giro
            log.warning("Controllo dopo la modifica delle esclusioni non riuscito")
        self.agent.send_diagnostics_soon()

    def _notify_services(self):
        try:
            return ha.notify_services()
        except ha.HAError:
            return []

    # ---- pagina ----

    @staticmethod
    def _toast(flash):
        """Conferma in basso, sempre visibile: spunta verde animata o X rossa. Solo CSS."""
        if not flash:
            return ""
        text, error = flash if isinstance(flash, tuple) else (flash, False)
        mark = ('<path class="mark" d="M18 18 L34 34 M34 18 L18 34"/>' if error
                else '<path class="mark" d="M15 27 L23 35 L38 18"/>')
        return (f'<div class="toast {"err" if error else "ok"}" role="{"alert" if error else "status"}">'
                f'<svg viewBox="0 0 52 52" aria-hidden="true"><circle class="ring" cx="26" cy="26" r="23"/>{mark}</svg>'
                f'<span>{esc(text)}</span></div>')

    def _ticket_html(self, t):
        """Una richiesta del cliente. Tutto arriva dal server: si fa l'escape di ogni campo
        e si scarta quello che non ha la forma prevista."""
        if not isinstance(t, dict) or not isinstance(t.get("id"), int):
            return ""
        status = t.get("status")
        msgs = ""
        for m in t.get("messages") if isinstance(t.get("messages"), list) else []:
            if not isinstance(m, dict):
                continue
            mine = m.get("author_type") == "cliente"
            msgs += (f'<div class="msg {"cliente" if mine else "installatore"}"><div class="meta">'
                     f'{"Tu" if mine else esc(m.get("author_name"))} · {fmt(m.get("created_at"))}</div>'
                     f'<p>{esc(m.get("text"))}</p></div>')
        badge = status if status in TICKET_LABELS else "off"
        return (f'<details{" open" if status != "chiuso" else ""}><summary><b>{esc(t.get("title"))}</b> '
                f'<span class="badge {badge}">{esc(TICKET_LABELS.get(status, status))}</span> '
                f'<span class="muted small">{fmt(t.get("updated_at"))}</span></summary>{msgs}'
                f'<form method="post" action="rispondi" class="row" style="margin-top:10px">{self._hidden()}'
                f'<input type="hidden" name="tid" value="{t["id"]}"><input name="text" placeholder="Aggiungi un messaggio" style="flex:1">'
                f'<button class="btn ghost">Invia</button></form></details>')

    def page(self):
        s = self.agent.state.snapshot()
        name = s.get("server_name") or "Assistenza"
        conn_label, conn_cls = CONNECTION_LABELS.get(s.get("connection"), ("Sconosciuto", "off"))
        paired = bool(s.get("token")) and s.get("connection") not in ("revocato",)
        flash, self.flash = self.flash, None
        color = s.get("brand_color") or ""
        brand_css = f"<style>:root{{--brand:{color}}}</style>" if re.fullmatch(r"#[0-9a-fA-F]{6}", color) else ""

        tickets_html = ""
        if paired:
            try:
                tickets = self.agent.link.tickets()
            except ServerError as e:
                tickets = None
                if e.status in (401, 426):
                    self.agent._handle_server_error(e)
                    return self.page()  # ridisegna con lo stato aggiornato (revocato / da aggiornare)
                tickets_html = f'<p class="muted">Richieste non disponibili: {esc(e)}</p>'
            if tickets is not None:
                shown, hidden = filter_tickets(tickets, s.get("ticket_retention"))
                for tk in shown:
                    tickets_html += self._ticket_html(tk)
                if not tickets:
                    tickets_html = '<p class="muted">Nessuna richiesta finora.</p>'
                elif hidden:
                    tickets_html += (f'<p class="muted small">{hidden} richiest{"a chiusa nascosta" if hidden == 1 else "e chiuse nascoste"} '
                                     'secondo le tue preferenze. L&#39;installatore ne conserva comunque lo storico.</p>')
                ret = s.get("ticket_retention") or {}
                def opt(options, current, first):
                    return f'<option value="">{first}</option>' + "".join(
                        f'<option value="{k}"{" selected" if str(current) == k else ""}>{v}</option>' for k, v in options.items())
                tickets_html += (
                    f'<details><summary class="small">Quali richieste chiuse mostrare</summary>'
                    f'<form method="post" action="richieste" class="row" style="margin-top:8px">{self._hidden()}'
                    f'<label style="margin:0">Chiuse negli ultimi</label><select name="days" style="width:auto">'
                    f'{opt(RETENTION_DAYS, ret.get("days"), "sempre")}</select>'
                    f'<label style="margin:0">al massimo</label><select name="max_closed" style="width:auto">'
                    f'{opt(RETENTION_KEEP, ret.get("max_closed"), "tutte")}</select>'
                    f'<button class="btn ghost small">Salva</button></form></details>')

        diag = s.get("last_diag") or {}
        diag_html = '<p class="muted">Nessun controllo eseguito.</p>'
        if diag:
            st = diag.get("status", "ok")
            items = "".join(f'<li>{esc(i.get("message"))}</li>' for i in diag.get("issues", [])
                            if isinstance(i, dict) and i.get("severity") != "info")
            diag_html = (f'<p><span class="badge {esc(st)}">{esc(STATUS_LABELS.get(st, st))}</span> '
                         f'<span class="muted small">controllato il {fmt(diag.get("collected_at"))}</span></p>'
                         + (f"<ul>{items}</ul>" if items else ""))

        consent = self.agent.state.consent_active()
        until = self.agent.state.get("consent_until")
        if consent:
            when = f"fino al <b>{fmt_epoch(until)}</b>" if until else "<b>senza scadenza</b>"
            consent_html = (
                f'<form method="post" action="consenso" class="row">{self._hidden()}<input type="hidden" name="enabled" value="0">'
                f'<span style="flex:1">L&#39;installatore può controllare lo stato dell&#39;impianto ed eseguire verifiche '
                f'a distanza, {when}.</span><button class="btn ghost">Sospendi</button></form>')
        else:
            options = "".join(f'<option value="{k}"{" selected" if k == "24h" else ""}>{l}</option>'
                              for k, l in DURATION_LABELS)
            consent_html = (
                '<p style="margin:0 0 10px">Accesso remoto <b>sospeso</b>: l&#39;installatore vede solo se l&#39;impianto è acceso.</p>'
                f'<form method="post" action="consenso" class="row">{self._hidden()}<input type="hidden" name="enabled" value="1">'
                f'<label for="durata" style="margin:0">Attiva per</label><select id="durata" name="durata" style="width:auto">{options}</select>'
                '<button class="btn">Attiva</button></form>')

        entities_html = ""
        if paired:
            excluded = s.get("excluded") or []
            flagged = [f for f in (s.get("flagged") or []) if isinstance(f, dict)]
            rows = "".join(
                f'<li><span class="grow">{esc(f.get("name"))} <span class="muted small">· {esc(f.get("reason"))}</span>'
                f'<br><code>{esc(f.get("entity_id"))}</code></span>'
                f'<form method="post" action="escludi">{self._hidden()}<input type="hidden" name="entity" value="{esc(f.get("entity_id"))}">'
                f'<button class="btn ghost small">Non controllare</button></form></li>' for f in flagged[:50])
            ex_rows = "".join(
                f'<li><span class="grow"><code>{esc(p)}</code></span>'
                f'<form method="post" action="includi">{self._hidden()}<input type="hidden" name="entity" value="{esc(p)}">'
                f'<button class="btn ghost small">Controlla di nuovo</button></form></li>' for p in excluded)
            entities_html = f"""<div class="card"><h2>Cosa controlla l'installatore</h2>
<p class="muted small" style="margin-top:0">Alcune entità segnalano sempre un problema anche se va tutto bene (la batteria del telefono,
un robot spesso spento...). Puoi escluderle: l'installatore non le vedrà più e vedrà solo quante ne hai escluse.</p>
{f'<p style="margin:12px 0 0"><b>Segnalate dall&#39;ultimo controllo</b></p><ul class="list">{rows}</ul>' if rows else '<p class="muted small">Nessuna entità segnalata dall&#39;ultimo controllo.</p>'}
{f'<p style="margin:16px 0 0"><b>Escluse</b></p><ul class="list">{ex_rows}</ul>' if ex_rows else ''}
<details><summary class="small">Escludi un&#39;entità a mano</summary>
<form method="post" action="escludi" class="row" style="margin-top:8px">{self._hidden()}
<input name="entity" placeholder="es. sensor.telefono_batteria oppure vacuum.robot_*" style="flex:1" required>
<button class="btn ghost small">Escludi</button></form></details></div>"""

        notify_html = ""
        if paired:
            ns = s.get("notify") or {}
            services = self._notify_services()
            chosen = set(ns.get("services") or [])
            svc_html = "".join(
                f'<label class="check"><input type="checkbox" name="service" value="{esc(x)}"{" checked" if x in chosen else ""}> '
                f'{esc(x.replace("mobile_app_", "App sul telefono: ").replace("_", " "))}</label>' for x in services)
            notify_html = f"""<div class="card"><h2>Notifiche</h2>
<p class="muted small" style="margin-top:0">Quando l&#39;installatore risponde o aggiorna una tua richiesta.</p>
<form method="post" action="notifiche">{self._hidden()}
<label class="check"><input type="checkbox" name="ha" value="1"{" checked" if ns.get("ha", True) else ""}> Nella campanella di Home Assistant</label>
{svc_html or '<p class="muted small">Per riceverle anche sul telefono installa l&#39;app di Home Assistant: comparirà qui.</p>'}
<div class="row" style="margin-top:10px"><button class="btn ghost small">Salva</button>
<button class="btn ghost small" name="prova" value="1">Salva e invia una prova</button></div></form></div>"""

        error_html = ""
        if s.get("connection") in ("errore", "non_configurato", "aggiornare", "revocato"):
            hint = s.get("last_error") or "Inserisci indirizzo del server e codice di abbinamento nella configurazione dell'add-on."
            error_html = f'<div class="card"><h2>Collegamento</h2><p style="margin:0">{esc(hint)}</p></div>'

        ticket_form = ""
        if paired:
            ticket_form = f"""<div class="card"><h2>Chiedi assistenza</h2>
<form method="post" action="ticket">{self._hidden()}<label for="title">Qual è il problema?</label>
<input id="title" name="title" required placeholder="Es. le luci del giardino non si accendono">
<label for="description">Descrizione</label><textarea id="description" name="description" placeholder="Da quando succede, cosa hai già provato..."></textarea>
<label for="contact">Come ti ricontattiamo? (facoltativo)</label><input id="contact" name="contact" placeholder="Telefono o email">
<p class="muted small">{"Alla richiesta viene allegato un controllo automatico dell&#39;impianto." if consent else ""}</p>
<button class="btn">Invia richiesta</button></form></div>"""

        return f"""<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(name)}</title><style>{CSS}</style>{brand_css}</head><body><main>
<div class="head"><div><p class="muted small" style="margin:0">Assistenza impianto</p><h1>{esc(name)}</h1></div>
<span class="badge {conn_cls}">{conn_label}</span></div>
{self._toast(flash)}
{error_html}
{ticket_form}
{f'<div class="card"><h2>Le tue richieste</h2>{tickets_html}</div>' if paired else ""}
<div class="card"><div class="head"><h2>Stato dell'impianto</h2>
<form method="post" action="diagnostica">{self._hidden()}<button class="btn ghost">Controlla ora</button></form></div>{diag_html}</div>
{f'<div class="card"><h2>Accesso remoto</h2>{consent_html}</div>' if paired else ""}
{entities_html}
{notify_html}
</main></body></html>"""
