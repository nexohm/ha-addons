# Agente Assistenza

🇮🇹 Italiano · [English below](#english)

Collega questo Home Assistant al servizio di assistenza del tuo installatore. Nella barra laterale compare il
pannello **Assistenza**, con il nome e il colore della sua azienda.

## Configurazione

1. Il tuo installatore ti fornisce **indirizzo del server** e **codice di abbinamento** (vale 24 ore), oppure li
   inserisce lui durante l'intervento.
2. Inseriscili nella scheda **Configurazione** e avvia l'add-on.
3. Nella barra laterale compare **Assistenza**.

| Opzione | Cosa indicare |
|---|---|
| Indirizzo del server di assistenza | es. `https://assistenza.rossiimpianti.it` |
| Codice di abbinamento | il codice di 8 caratteri dato dall'installatore |
| Intervallo di collegamento | ogni quanti secondi l'agente comunica che l'impianto è acceso (predefinito 60) |
| Intervallo di controllo | ogni quanti minuti esegue il controllo automatico (predefinito 15) |

L'indirizzo deve iniziare con `https://`: il collegamento è cifrato. Un indirizzo `http://` è accettato solo se il
server si trova nella rete di casa. Dopo l'abbinamento il codice non serve più.

## Il pannello Assistenza

- **Richieste**: apri una richiesta di assistenza (il controllo dell'impianto viene allegato), leggi le risposte e
  rispondi. Il numero sulla scheda indica le richieste ancora aperte.
- **Impianto**: stato del collegamento e dell'ultimo controllo; **accesso remoto** a tempo (1 ora, 4 ore, 24 ore,
  7 giorni o senza scadenza) oppure sospeso; **cosa controlla l'installatore**; **accesso amministratore**.
- **Preferenze**: dove ricevere le notifiche (campanella di Home Assistant e/o telefono con l'app di Home Assistant
  o altri servizi `notify`) e quante richieste chiuse tenere nel pannello.

## Cosa vede l'installatore

- se l'impianto è acceso e collegato;
- un controllo automatico: dispositivi non raggiungibili, batterie scariche, aggiornamenti disponibili, automazioni
  spente, spazio su disco, data dell'ultimo backup.

**Non vede** telecamere, posizione delle persone, cronologia né i tuoi dati personali, e **non può** modificare la
configurazione: l'agente esegue solo i comandi di controllo previsti.

Puoi decidere cosa controllare dalla scheda **Impianto**:
- **escludi** singole entità o gruppi con `*` (es. `sensor.telefono_*`): non vengono controllate né nominate;
- oppure fai controllare **solo le entità con certe etichette** di Home Assistant (dell'entità o del suo
  dispositivo). Se le etichette non si possono leggere, il controllo salta un giro invece di includere altro.

## Accesso amministratore (solo se lo concedi tu)

Se l'installatore deve correggere qualcosa nel tuo Home Assistant, può chiederti l'**accesso amministratore**:
ricevi una notifica con il nome del tecnico e dell'azienda. Lo concedi (o rifiuti) dalla scheda **Impianto**,
scegliendo per quanto tempo: 1 ora, 4 ore, 24 ore, 7 giorni o senza scadenza.

- L'agente crea un utente apposta (`assistenza_…`) solo quando l'installatore entra, ogni volta con una password
  nuova: le password e le sessioni precedenti smettono di funzionare.
- Ricevi una notifica ogni volta che l'installatore entra, e puoi chiudere l'accesso quando vuoi.
- Alla scadenza l'utente viene cancellato dall'agente, anche se il server dell'installatore non è raggiungibile.
- **Senza scadenza**: ogni 30 giorni ricevi un promemoria; se l'installatore non entra per 30 giorni il suo utente
  viene cancellato (l'accesso resta concesso finché non lo chiudi).
- L'utente viene cancellato anche se arresti o disinstalli l'add-on, se l'installatore scollega l'impianto o se
  l'assistenza viene sospesa.

## Sospendere l'assistenza

Dalla scheda **Impianto** puoi sospendere l'accesso remoto in qualsiasi momento: l'installatore vede solo se
l'impianto è acceso e nessun controllo viene eseguito. Per scollegare del tutto l'impianto basta arrestare o
disinstallare l'add-on.

Se il pannello mostra **«Assistenza sospesa»**, è il servizio dell'installatore a essere momentaneamente sospeso:
l'impianto resta abbinato e il collegamento riprende da solo appena viene riattivato.

---

<a id="english"></a>

# Support Agent (English)

Connects this Home Assistant to your installer's support service. An **Assistenza** (Support) panel appears in the
sidebar, branded with the installer company's name and colour. The panel is in Italian.

## Configuration

1. Your installer gives you the **server address** and a **pairing code** (valid for 24 hours), or enters them
   during the visit.
2. Enter them in the **Configuration** tab and start the add-on.
3. **Assistenza** appears in the sidebar.

| Option | What to enter |
|---|---|
| Support server address | e.g. `https://support.example-installer.com` |
| Pairing code | the 8-character code from the installer |
| Connection interval | how often (seconds) the agent reports the system is up (default 60) |
| Check interval | how often (minutes) the automatic check runs (default 15) |

The address must start with `https://`: the connection is encrypted. An `http://` address is accepted only for a
server on the home network. After pairing the code is no longer needed.

## The Support panel

- **Richieste** (Requests): open a support request (the system check is attached), read replies and answer. The
  number on the tab shows the requests still open.
- **Impianto** (System): connection and last check status; time-limited **remote access** (1 hour, 4 hours,
  24 hours, 7 days or no expiry) or suspended; **what the installer checks**; **administrator access**.
- **Preferenze** (Preferences): where notifications go (Home Assistant bell and/or phone through the Home Assistant
  app or other `notify` services) and how many closed requests to keep in the panel.

## What the installer sees

- whether the system is up and connected;
- an automatic check: unreachable devices, low batteries, pending updates, disabled automations, disk space, date
  of the last backup.

The installer **does not see** cameras, people's locations, history or your personal data, and **cannot** change the
configuration: the agent only runs the predefined check commands.

You decide what may be checked from the **Impianto** tab:
- **exclude** single entities or groups with `*` (e.g. `sensor.phone_*`): they are neither checked nor named;
- or allow checks **only on entities with given Home Assistant labels** (on the entity or its device). If labels
  cannot be read, the check skips a round rather than including anything else.

## Administrator access (only if you grant it)

If the installer needs to fix something in your Home Assistant, they can ask for **administrator access**: you get a
notification with the technician's and company's name. You grant (or decline) it from the **Impianto** tab, choosing
how long: 1 hour, 4 hours, 24 hours, 7 days or no expiry.

- The agent creates a dedicated user (`assistenza_…`) only when the installer logs in, each time with a new
  password: earlier passwords and sessions stop working.
- You are notified every time the installer logs in, and you can close access at any time.
- When the time is up the agent deletes the user, even if the installer's server is unreachable.
- **No expiry**: you get a reminder every 30 days; if the installer does not log in for 30 days their user is
  deleted (access stays granted until you close it).
- The user is also deleted if you stop or uninstall the add-on, if the installer disconnects the system or if
  support is suspended.

## Suspending support

From the **Impianto** tab you can suspend remote access at any time: the installer only sees whether the system is
up and no checks run. To disconnect the system completely, stop or uninstall the add-on.

If the panel shows **"Assistenza sospesa"** (support suspended), the installer's service itself is temporarily
suspended: the system stays paired and the connection resumes on its own once it is reactivated.
