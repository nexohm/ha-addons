"""Diagnostica dell'impianto: raccoglie lo stato di Home Assistant e lo riassume in problemi.

Per aggiungere un controllo: calcola il dato in collect(), poi aggiungi un issue() con
severità "critico", "attenzione" o "info". Lo stato generale è il problema più grave.
"""
import fnmatch
from datetime import datetime, timezone

from . import ha

LOW_BATTERY = 20       # % sotto cui una batteria è considerata scarica
MAX_ITEMS = 50         # elementi massimi elencati per ogni problema
SEVERITY_ORDER = {"critico": 2, "attenzione": 1, "info": 0}

# Domini che non hanno senso come "non disponibili" (sono comandi o eventi, non dispositivi).
IGNORE_UNAVAILABLE = {"button", "event", "scene", "script", "automation", "zone", "person", "update"}


def _n(count, singular, plural):
    return f"{count} {singular if count == 1 else plural}"


def _name(state):
    return state.get("attributes", {}).get("friendly_name") or state["entity_id"]


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse(ts):
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def is_excluded(entity_id, patterns):
    """Entità esclusa dal cliente: nome esatto oppure modello con * (es. sensor.robot_*)."""
    return any(fnmatch.fnmatchcase(entity_id, p) for p in patterns)


def collect(excluded=()):
    """Diagnostica da mandare al server. Le entità escluse dal cliente non vengono controllate né
    nominate. La chiave interna "_flagged" (entità segnalate, per il pannello del cliente) va
    tolta prima dell'invio: la toglie Agent.fresh_diagnostics."""
    now = datetime.now(timezone.utc)
    issues = []
    flagged = []
    excluded_count = 0

    def issue(severity, code, message, items=None):
        entry = {"severity": severity, "code": code, "message": message}
        if items:
            entry["items"] = items[:MAX_ITEMS]
        issues.append(entry)

    all_states = ha.states()

    unavailable, orphans, low_battery, updates, automations_off = [], [], [], [], []
    for s in all_states:
        eid = s["entity_id"]
        if excluded and is_excluded(eid, excluded):
            excluded_count += 1
            continue
        domain = eid.split(".", 1)[0]
        attrs = s.get("attributes", {})
        state = s.get("state")

        def flag(reason):
            flagged.append({"entity_id": eid, "name": _name(s), "reason": reason})

        if state == "unavailable" and domain not in IGNORE_UNAVAILABLE:
            # "restored" = entità rimasta nel registro ma la cui integrazione non la fornisce più
            (orphans if attrs.get("restored") else unavailable).append(eid)
            flag("orfana" if attrs.get("restored") else "non disponibile")

        if attrs.get("device_class") == "battery":
            level = _num(state)
            if domain == "sensor" and level is not None and level < LOW_BATTERY:
                low_battery.append(f"{_name(s)} ({level:.0f}%)")
                flag(f"batteria {level:.0f}%")
            elif domain == "binary_sensor" and state == "on":
                low_battery.append(f"{_name(s)} (scarica)")
                flag("batteria scarica")

        if domain == "update" and state == "on":
            installed, latest = attrs.get("installed_version"), attrs.get("latest_version")
            updates.append(f"{_name(s)} {installed or ''} → {latest or ''}".strip())

        if domain == "automation" and state == "off":
            automations_off.append(_name(s))
            flag("automazione disattivata")

    if unavailable:
        sev = "critico" if len(unavailable) > 10 else "attenzione"
        issue(sev, "unavailable_entities", _n(len(unavailable), "entità non disponibile", "entità non disponibili"), sorted(unavailable))
    if orphans:
        issue("info", "orphan_entities", _n(len(orphans), "entità orfana da ripulire", "entità orfane da ripulire"), sorted(orphans))
    if low_battery:
        issue("attenzione", "low_battery", _n(len(low_battery), "dispositivo con batteria scarica", "dispositivi con batteria scarica"), sorted(low_battery))
    if updates:
        issue("info", "updates", _n(len(updates), "aggiornamento disponibile", "aggiornamenti disponibili"), updates)
    if automations_off:
        issue("info", "automations_off", _n(len(automations_off), "automazione disattivata", "automazioni disattivate"), sorted(automations_off))

    # ---- sistema (Supervisor) ----
    system = {}
    core = ha.supervisor("core/info") or {}
    system["ha_version"] = core.get("version")
    if not system["ha_version"]:
        try:
            system["ha_version"] = ha.config().get("version")
        except ha.HAError:
            pass
    os_info = ha.supervisor("os/info") or {}
    system["os_version"] = os_info.get("version")

    host = ha.supervisor("host/info") or {}
    used, total = _num(host.get("disk_used")), _num(host.get("disk_total"))
    if used is not None and total:
        system["disk_used_gb"], system["disk_total_gb"] = round(used, 1), round(total, 1)
        pct = used / total * 100
        if pct >= 90:
            issue("critico", "disk_full", f"Disco quasi pieno ({pct:.0f}%)")
        elif pct >= 80:
            issue("attenzione", "disk_high", f"Disco occupato all'{pct:.0f}%")

    backups = ha.supervisor("backups")
    if backups is not None:
        dates = [d for d in (_parse(b.get("date")) for b in backups.get("backups", [])) if d]
        if dates:
            last = max(dates)
            age = (now - last).days
            system["last_backup"] = last.isoformat(timespec="seconds")
            system["last_backup_age_days"] = age
            if age > 30:
                issue("critico", "backup_old", f"Ultimo backup di {_n(age, 'giorno', 'giorni')} fa")
            elif age > 7:
                issue("attenzione", "backup_old", f"Ultimo backup di {_n(age, 'giorno', 'giorni')} fa")
        else:
            issue("critico", "backup_missing", "Nessun backup presente")

    issues.sort(key=lambda i: -SEVERITY_ORDER[i["severity"]])
    worst = max((SEVERITY_ORDER[i["severity"]] for i in issues), default=0)
    status = {2: "critico", 1: "attenzione", 0: "ok"}[worst]

    return {
        "collected_at": now.isoformat(timespec="seconds"),
        "status": status,
        "summary": {
            "entities": len(all_states),
            "unavailable": len(unavailable),
            "low_battery": len(low_battery),
            "updates": len(updates),
            "automations_off": len(automations_off),
            "excluded": excluded_count,
        },
        "system": system,
        "issues": issues,
        "_flagged": flagged[:200],
    }
