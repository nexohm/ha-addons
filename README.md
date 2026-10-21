# Nexohm — add-on per Home Assistant

🇮🇹 Italiano · [🇬🇧 English](README.en.md)

Questo repository contiene l'add-on **Agente Assistenza**, che collega l'Home Assistant di un cliente al server di
assistenza del suo installatore ([`nexohm/assist-server`](https://github.com/nexohm/assist-server)).

```
  SERVER DELL'INSTALLATORE                       CASA DEL CLIENTE
 ┌───────────────────────────┐            ┌──────────────────────────────────┐
 │ dashboard dell'installatore│◄── HTTPS ──│ Home Assistant + Agente Assistenza│
 └───────────────────────────┘            │ pannello «Assistenza» nella barra │
                                           └──────────────────────────────────┘
        è sempre l'agente a chiamare il server: in casa non si apre nessuna porta
```

## Cosa fa

**Per l'installatore**
- sa se l'impianto è acceso e collegato;
- riceve un **controllo automatico**: entità non disponibili o orfane, batterie scariche, aggiornamenti disponibili,
  automazioni spente, spazio su disco, età dell'ultimo backup;
- risponde alle richieste di assistenza del cliente;
- può entrare come **amministratore**, solo se il cliente lo concede e per il tempo che sceglie.

**Per il cliente**, nel pannello **Assistenza** della barra laterale (con nome e colore dell'azienda installatrice):
- scheda **Richieste**: apre una richiesta (con il controllo dell'impianto allegato), legge le risposte, riceve
  notifiche in Home Assistant o sul telefono quando l'installatore risponde o cambia lo stato;
- scheda **Impianto**: stato del collegamento, **accesso remoto a tempo** (1 ora, 4 ore, 24 ore, 7 giorni o senza
  scadenza) e sospensione in un clic, **entità escluse** dai controlli (anche con `*`, es. `vacuum.robot_*`) oppure
  controllo solo delle entità con certe **etichette**, concessione e chiusura dell'**accesso amministratore**;
- scheda **Preferenze**: notifiche (campanella di Home Assistant e/o servizi `notify`, come l'app sul telefono) e
  pulizia automatica delle richieste chiuse.

**Cosa l'installatore non vede e non può fare**: non vede telecamere, posizione delle persone, cronologia né dati
personali; senza l'accesso amministratore concesso dal cliente non può modificare nulla. L'agente esegue solo una
lista chiusa di comandi (`ping`, diagnostica, apertura e chiusura dell'accesso amministratore) e rifiuta tutto il resto.

## Installazione

Requisiti: Home Assistant **OS** o **Supervised** (servono gli add-on), su amd64, aarch64 (es. Raspberry Pi 4/5)
o armv7. L'installatore deve avere un server di assistenza ([guida](https://github.com/nexohm/assist-server#installazione-del-server)).

1. Nella dashboard dell'installatore: crea il cliente e l'impianto e copia il **codice di abbinamento**
   (vale 24 ore) e l'**indirizzo del server**.
2. In Home Assistant: **Impostazioni → Componenti aggiuntivi → Store → ⋮ → Repository**, aggiungi
   `https://github.com/nexohm/ha-addons` e chiudi.
3. Cerca **Agente Assistenza** e installalo.
4. Nella scheda **Configurazione** inserisci:

   | Opzione | Valore |
   |---|---|
   | Indirizzo del server di assistenza | es. `https://assistenza.rossiimpianti.it` |
   | Codice di abbinamento | il codice di 8 caratteri (es. `ABCD-2345`) |
   | Intervallo di collegamento | ogni quanti secondi l'agente si fa sentire (predefinito 60) |
   | Intervallo di controllo | ogni quanti minuti esegue il controllo automatico (predefinito 15) |

5. **Avvia** l'add-on. In pochi secondi l'impianto risulta online nella dashboard e nella barra laterale compare
   **Assistenza**.

L'indirizzo del server deve iniziare con `https://`; `http://` è accettato solo per un server nella rete di casa.
Dopo l'abbinamento il codice non serve più: l'agente usa un token personale.

## Accesso amministratore temporaneo

1. L'installatore lo **chiede** dalla dashboard: il cliente riceve una notifica.
2. Il cliente lo **concede** dalla scheda *Impianto* scegliendo la durata, oppure lo rifiuta.
3. Quando l'installatore entra, l'agente crea un utente `assistenza_…` con una password nuova, mai salvata; ogni
   nuova password ricrea l'utente e chiude le sessioni precedenti. Il cliente riceve una notifica a ogni ingresso.
4. L'utente viene **cancellato dall'agente** alla scadenza (anche se il server non risponde), quando il cliente chiude
   l'accesso, all'arresto dell'add-on, alla revoca dell'impianto o alla sospensione dell'assistenza.
5. Senza scadenza: utente cancellato dopo 30 giorni senza ingressi e promemoria al cliente ogni 30 giorni.

## Aggiornamenti

Gli aggiornamenti arrivano da Home Assistant come per ogni add-on (**Impostazioni → Componenti aggiuntivi**).
Le novità di ogni versione sono nel [CHANGELOG](installer_agent/CHANGELOG.md).

## Sviluppo

- L'add-on è in Python standard, senza dipendenze esterne (`installer_agent/agent`).
- I test completi (agente + server + finto Home Assistant) sono nel repository del server:
  `tests/run_e2e.sh` e `tests/run_security.sh` di [`nexohm/assist-server`](https://github.com/nexohm/assist-server#sviluppo-prove-e-rilasci).
- Si lavora sul branch **`sviluppo`** con versioni `X.Y.Z-devN` e nome «Agente Assistenza (prova)»: per provarle in
  Home Assistant aggiungi il repository `https://github.com/nexohm/ha-addons#sviluppo` (con l'add-on normale fermo).
- Prima del merge su **`main`** (protetto, solo tramite pull request) si imposta la versione definitiva e il nome
  normale: il workflow lo controlla e pubblica le immagini per amd64, aarch64 e armv7 su `ghcr.io/nexohm`.
