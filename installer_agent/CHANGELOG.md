# Changelog

## 0.1.8 (in sviluppo)
- Pannello diviso in tre schede: Richieste, Impianto, Preferenze. La pagina è molto più corta e il
  numero sulla scheda Richieste indica le richieste ancora aperte.
- Dopo ogni salvataggio il pannello torna alla sezione appena usata invece che all'inizio della pagina
  (per esempio escludendo un'entità la lista resta dov'era).
- Controllo solo delle entità con certe etichette di Home Assistant (dell'entità o del suo dispositivo):
  le altre non vengono controllate né nominate all'installatore. Se le etichette non si possono leggere,
  il controllo salta il giro invece di mandare entità escluse.
- Il modulo per una nuova richiesta resta chiuso quando ce n'è già una in corso.
- Accesso amministratore temporaneo per l'installatore, solo se il cliente lo concede (1 ora, 4 ore,
  24 ore, 7 giorni o senza scadenza). L'utente in HA viene creato a ogni ingresso con una password nuova
  (mai salvata), cancellato alla scadenza anche senza server, all'arresto dell'add-on e, senza scadenza,
  dopo 30 giorni di inutilizzo; promemoria mensile e notifica al cliente a ogni ingresso.
- Le notifiche al cliente dicono anche quale tecnico agisce, oltre al nome dell'azienda: chi chiede
  l'accesso amministratore, chi entra, chi lo chiude, chi risponde a una richiesta e chi la prende in
  carico. Anche l'utente creato in Home Assistant porta il nome del tecnico. Con un server più vecchio
  resta solo il nome dell'azienda.
- Tolta la barra di scorrimento che compariva accanto alle schede del pannello.

## 0.1.7
- Il cliente può escludere entità dai controlli dell'installatore (anche con *, es. vacuum.robot_*):
  non vengono più controllate né nominate, l'installatore vede solo quante sono.
- Il cliente sceglie quali richieste chiuse vedere (ultimi 7/30/90 giorni, al massimo N): le altre
  spariscono dal pannello, l'installatore conserva lo storico.
- Notifiche al cliente quando l'installatore risponde o cambia stato a una richiesta: nella campanella
  di Home Assistant e/o sul telefono (app di HA o altri servizi notify).
- Conferme animate e sempre visibili nel pannello (spunta verde, X rossa per gli errori).

## 0.1.6
- Indirizzi di Home Assistant letti come nella schermata Impostazioni → Sistema → Rete (API websocket):
  funziona anche con rete locale "Automatico" e con Home Assistant Cloud (Nabu Casa), prima risultavano vuoti.

## 0.1.5
- Comunica al server gli indirizzi (interno ed esterno) di Home Assistant impostati in
  Impostazioni → Sistema → Rete: l'installatore li trova come pulsante "Apri Home Assistant".
- Contiene tutte le correzioni di sicurezza della 0.1.4.

## 0.1.4 — sicurezza
- Il pannello "Assistenza" tratta come non fidato tutto ciò che arriva dal server: ogni testo viene
  ripulito e una Content-Security-Policy impedisce l'esecuzione di qualsiasi script nel pannello.
- Protezione anti-CSRF sui moduli del pannello: un altro sito non può riattivare l'accesso remoto
  o aprire richieste al posto del cliente.
- L'agente non segue più i reindirizzamenti del server (avrebbe inviato il token anche a un altro indirizzo).
- L'indirizzo del server deve usare https://; http è ammesso solo per server nella rete locale.
- Risposte del server malformate o troppo grandi non bloccano più l'agente né il pannello.

## 0.1.3
- Accesso remoto a tempo: il cliente sceglie per quanto attivarlo (1 ora, 4 ore, 24 ore, 7 giorni o senza scadenza).
  Allo scadere l'agente lo sospende da solo e lo comunica al server.
- Nuove icona e logo dell'add-on.

## 0.1.2
- Corretto: la diagnostica falliva con "401 Unauthorized" perché la chiave del Supervisor non veniva
  letta dove la salva s6-overlay (/run/s6/container_environment).
- All'avvio il log dice se la chiave è stata trovata e dove.

## 0.1.1
- L'agente si presenta come "NexohmAgent": i filtri anti-bot (es. Cloudflare) non lo bloccano più.
- Messaggio chiaro quando la richiesta viene bloccata da Cloudflare o da un proxy prima di arrivare al server.
- Un errore che arriva dal proxy e non dal server non cancella più l'abbinamento.

## 0.1.0
- Prima versione: abbinamento, battito, diagnostica, ticket, comandi `ping` e `run_diagnostics`, consenso del cliente.
