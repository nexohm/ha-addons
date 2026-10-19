# Changelog

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
