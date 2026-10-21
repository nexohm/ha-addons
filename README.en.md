# Nexohm — Home Assistant add-ons

[🇮🇹 Italiano](README.md) · 🇬🇧 English

This repository contains the **Agente Assistenza** (Support Agent) add-on, which connects a customer's Home
Assistant to their installer's support server ([`nexohm/assist-server`](https://github.com/nexohm/assist-server)).

```
  INSTALLER'S SERVER                          CUSTOMER'S HOME
 ┌───────────────────────────┐            ┌──────────────────────────────────┐
 │ installer dashboard       │◄── HTTPS ──│ Home Assistant + Support Agent   │
 └───────────────────────────┘            │ "Assistenza" panel in the sidebar│
                                           └──────────────────────────────────┘
        the agent always calls the server: no port is opened at home
```

The add-on interface is currently in **Italian**.

## What it does

**For the installer**
- knows whether the system is up and connected;
- receives an **automatic health check**: unavailable or orphaned entities, low batteries, pending updates,
  disabled automations, disk space, age of the last backup;
- answers the customer's support requests;
- can log in as an **administrator**, only if the customer allows it and for as long as they choose.

**For the customer**, in the **Assistenza** (Support) sidebar panel, branded with the installer company's name and
colour:
- **Richieste** (Requests) tab: open a request (with the system check attached), read replies, get notifications in
  Home Assistant or on the phone when the installer replies or changes the status;
- **Impianto** (System) tab: connection status, **time-limited remote access** (1 hour, 4 hours, 24 hours, 7 days or
  no expiry) and one-click suspension, **excluded entities** (wildcards allowed, e.g. `vacuum.robot_*`) or checks
  limited to entities with given **labels**, granting and closing **administrator access**;
- **Preferenze** (Preferences) tab: notifications (Home Assistant bell and/or `notify` services such as the phone
  app) and automatic clean-up of closed requests.

**What the installer cannot see or do**: no cameras, people's locations, history or personal data; without
administrator access granted by the customer they cannot change anything. The agent only runs a closed list of
commands (`ping`, diagnostics, opening and closing administrator access) and refuses everything else.

## Installation

Requirements: Home Assistant **OS** or **Supervised** (add-ons are required), on amd64, aarch64 (e.g. Raspberry Pi
4/5) or armv7. The installer needs a support server ([guide](https://github.com/nexohm/assist-server/blob/main/README.en.md#installing-the-server)).

1. In the installer's dashboard: create the customer and the system and copy the **pairing code** (valid for
   24 hours) and the **server address**.
2. In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, add
   `https://github.com/nexohm/ha-addons` and close.
3. Find **Agente Assistenza** and install it.
4. In the **Configuration** tab enter:

   | Option | Value |
   |---|---|
   | Support server address | e.g. `https://support.example-installer.com` |
   | Pairing code | the 8-character code (e.g. `ABCD-2345`) |
   | Connection interval | how often (seconds) the agent checks in (default 60) |
   | Check interval | how often (minutes) the automatic check runs (default 15) |

5. **Start** the add-on. Within seconds the system shows as online in the dashboard and **Assistenza** appears in
   the sidebar.

The server address must start with `https://`; `http://` is only accepted for a server on the home network.
After pairing the code is no longer needed: the agent uses a personal token.

## Temporary administrator access

1. The installer **asks** for it from the dashboard: the customer gets a notification.
2. The customer **grants** it from the *Impianto* tab choosing the duration, or declines.
3. When the installer logs in, the agent creates an `assistenza_…` user with a new password that is never stored;
   each new password recreates the user and ends previous sessions. The customer is notified at every login.
4. The **agent deletes the user** when the time is up (even if the server is unreachable), when the customer closes
   access, when the add-on stops, when the system is revoked or when support is suspended.
5. No expiry: the user is deleted after 30 days without logins and the customer gets a reminder every 30 days.

## Updates

Updates arrive through Home Assistant like any add-on (**Settings → Add-ons**). What changed in each version is in
the [CHANGELOG](installer_agent/CHANGELOG.md) (Italian).

## Development

- The add-on is plain Python with no external dependencies (`installer_agent/agent`).
- The full tests (agent + server + fake Home Assistant) live in the server repository: `tests/run_e2e.sh` and
  `tests/run_security.sh` in [`nexohm/assist-server`](https://github.com/nexohm/assist-server/blob/main/README.en.md#development-testing-and-releases).
- Work happens on the **`sviluppo`** branch with `X.Y.Z-devN` versions named "Agente Assistenza (prova)": to try
  them in Home Assistant add the repository `https://github.com/nexohm/ha-addons#sviluppo` (with the normal add-on
  stopped).
- Before merging into **`main`** (protected, pull requests only) the final version and normal name are set: the
  workflow checks this and publishes images for amd64, aarch64 and armv7 to `ghcr.io/nexohm`.
