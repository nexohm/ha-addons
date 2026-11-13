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


UPDATE_INSTALL = 1   # supported_features delle entità update: si può installare da remoto


def update_kind(entity_id, attrs):
    """Che cosa aggiorna un'entità update: Home Assistant, sistema operativo, Supervisor, add-on o altro
    (integrazioni HACS, firmware di dispositivi, ESPHome...)."""
    if entity_id == "update.home_assistant_core_update":
        return "core"
    if entity_id == "update.home_assistant_operating_system_update":
        return "os"
    if entity_id == "update.home_assistant_supervisor_update":
        return "supervisor"
    if "/hassio/addons/" in str(attrs.get("entity_picture") or ""):
        return "addon"
    return "altro"


def _location(agent_id):
    """Dove è salvato un backup, in parole semplici."""
    if agent_id in ("hassio.local", "backup.local"):
        return "Questo dispositivo"
    if agent_id == "cloud.cloud":
        return "Home Assistant Cloud"
    return str(agent_id).split(".", 1)[-1][:60]


def backup_status(supervisor_backups=None):
    """Backup presenti e stato del backup automatico.

    Da Home Assistant 2025.1 il sistema di backup (backup/info) conosce anche le posizioni esterne (NAS,
    cloud) e il backup automatico; con versioni precedenti si usa l'elenco del Supervisor."""
    out = {"items": [], "automatic": None}
    try:
        info = ha.ws_command("backup/info", timeout=15)
    except ha.HAError:
        info = None
    if isinstance(info, dict) and isinstance(info.get("backups"), list):
        for b in info["backups"]:
            if not isinstance(b, dict):
                continue
            agents = b.get("agents") if isinstance(b.get("agents"), dict) else {a: {} for a in b.get("agent_ids") or []}
            sizes = [v.get("size") for v in agents.values() if isinstance(v, dict) and isinstance(v.get("size"), (int, float))]
            size = b.get("size") if isinstance(b.get("size"), (int, float)) else (max(sizes) if sizes else None)
            # completo = configurazione di Home Assistant con il suo database (gli add-on possono mancare)
            full = b.get("homeassistant_included") is not False and b.get("database_included") is not False
            out["items"].append({"name": str(b.get("name") or "")[:80], "date": b.get("date"),
                                 "size_mb": round(size / 1048576, 1) if size else None,
                                 "kind": "completo" if full else "parziale",
                                 "locations": [_location(a) for a in agents][:5],
                                 "automatic": bool(b.get("with_automatic_settings")),
                                 "protected": bool(b.get("protected"))})
        auto = {k: info.get(k) for k in ("last_attempted_automatic_backup", "last_completed_automatic_backup",
                                         "next_automatic_backup") if isinstance(info.get(k), str)}
        try:
            cfg = (ha.ws_command("backup/config/info", timeout=15) or {}).get("config") or {}
        except ha.HAError:
            cfg = {}
        schedule = cfg.get("schedule") if isinstance(cfg.get("schedule"), dict) else {}
        retention = cfg.get("retention") if isinstance(cfg.get("retention"), dict) else {}
        create = cfg.get("create_backup") if isinstance(cfg.get("create_backup"), dict) else {}
        auto.update(recurrence=schedule.get("recurrence") if isinstance(schedule.get("recurrence"), str) else None,
                    days=[d for d in schedule.get("days") or [] if isinstance(d, str)][:7],
                    time=schedule.get("time") if isinstance(schedule.get("time"), str) else None,
                    copies=retention.get("copies") if isinstance(retention.get("copies"), int) else None,
                    retention_days=retention.get("days") if isinstance(retention.get("days"), int) else None,
                    locations=[_location(a) for a in create.get("agent_ids") or []][:5])
        out["automatic"] = auto
    elif supervisor_backups:
        for b in supervisor_backups:
            if not isinstance(b, dict):
                continue
            locs = b.get("locations") or [b.get("location")]
            out["items"].append({"name": str(b.get("name") or "")[:80], "date": b.get("date"),
                                 "size_mb": b.get("size") if isinstance(b.get("size"), (int, float)) else None,
                                 "kind": "completo" if b.get("type") == "full" else "parziale",
                                 "locations": ["Questo dispositivo" if not l or l == ".local" else str(l)[:60] for l in locs][:5],
                                 "automatic": None, "protected": bool(b.get("protected"))})
    out["items"].sort(key=lambda i: str(i.get("date") or ""), reverse=True)
    out["items"] = out["items"][:15]
    return out


def is_excluded(entity_id, patterns):
    """Entità esclusa dal cliente: nome esatto oppure modello con * (es. sensor.robot_*)."""
    return any(fnmatch.fnmatchcase(entity_id, p) for p in patterns)


def collect(excluded=(), only_labels=None, labels_of=None):
    """Diagnostica da mandare al server. Le entità escluse dal cliente non vengono controllate né
    nominate; con only_labels vengono controllate solo le entità che hanno almeno una di quelle
    etichette (labels_of: {entity_id: {etichette}}). La chiave interna "_flagged" (entità segnalate, per il pannello del cliente) va
    tolta prima dell'invio: la toglie Agent.fresh_diagnostics."""
    now = datetime.now(timezone.utc)
    issues = []
    flagged = []
    excluded_count = 0

    names = {}   # nome leggibile delle entità nominate, per l'elenco della dashboard dell'installatore

    def issue(severity, code, message, items=None):
        entry = {"severity": severity, "code": code, "message": message}
        if items:
            entry["items"] = items[:MAX_ITEMS]
            known = {i: names[i] for i in entry["items"] if i in names}
            if known:
                entry["names"] = known
        issues.append(entry)

    all_states = ha.states()

    unavailable, orphans, low_battery, updates, automations_off = [], [], [], [], []
    updates_list = []   # aggiornamenti in forma strutturata: l'installatore li può installare da remoto
    for s in all_states:
        eid = s["entity_id"]
        if excluded and is_excluded(eid, excluded):
            excluded_count += 1
            continue
        # "Controlla solo le entità con queste etichette" (dell'entità o del suo dispositivo)
        if only_labels and not (labels_of.get(eid, set()) & set(only_labels)):
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
            if attrs.get("friendly_name"):
                names[eid] = str(attrs["friendly_name"])[:120]
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
            updates_list.append({"entity_id": eid, "title": str(attrs.get("title") or _name(s))[:80],
                                 "installed": str(installed or "")[:40], "latest": str(latest or "")[:40],
                                 "kind": update_kind(eid, attrs), "in_progress": bool(attrs.get("in_progress")),
                                 "installable": bool(int(attrs.get("supported_features") or 0) & UPDATE_INSTALL)})

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
    backups_info = backup_status((backups or {}).get("backups"))
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
        "updates_list": updates_list[:50],
        "backups": backups_info,
        "_flagged": flagged[:200],
    }
