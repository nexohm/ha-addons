# Changelog

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
