# Agente Assistenza

Collega questo Home Assistant al servizio di assistenza del tuo installatore.

## Configurazione

1. Il tuo installatore ti fornisce **indirizzo del server** e **codice di abbinamento**
   (oppure li inserisce lui durante l'intervento).
2. Inseriscili nella scheda *Configurazione* e avvia l'add-on.
3. Nella barra laterale compare la voce **Assistenza**.

L'indirizzo del server deve iniziare con `https://`: il collegamento è cifrato. Un indirizzo
`http://` è accettato solo se il server si trova nella rete di casa (es. `http://192.168.1.10:8080`).

## Cosa vede l'installatore

- se l'impianto è acceso e collegato;
- un controllo automatico: dispositivi non raggiungibili, batterie scariche, aggiornamenti
  disponibili, spazio su disco, data dell'ultimo backup.

**Non vede** telecamere, posizione delle persone, cronologia né i tuoi dati personali, e
**non può** modificare la configurazione: l'agente esegue solo i comandi di controllo previsti.

## Accesso amministratore (solo se lo concedi tu)

Se l'installatore deve correggere qualcosa nel tuo Home Assistant, può chiederti l'**accesso
amministratore**. Lo concedi (o rifiuti) dal pannello **Assistenza**, scheda **Impianto**, scegliendo
per quanto tempo: 1 ora, 4 ore, 24 ore, 7 giorni o senza scadenza.

- L'agente crea un utente apposta (`assistenza_…`) solo quando l'installatore entra, ogni volta con una
  password nuova: le password e le sessioni precedenti smettono di funzionare.
- Ricevi una notifica ogni volta che l'installatore entra, e puoi chiudere l'accesso quando vuoi.
- Alla scadenza l'utente viene cancellato dall'agente, anche se il server dell'installatore non è raggiungibile.
- **Senza scadenza**: ogni 30 giorni ricevi un promemoria; se l'installatore non entra per 30 giorni,
  il suo utente viene cancellato (l'accesso resta concesso finché non lo chiudi).
- Se arresti o disinstalli l'add-on, l'utente dell'installatore viene cancellato.

## Sospendere l'accesso

Dal pannello **Assistenza** puoi sospendere l'accesso remoto in qualsiasi momento (l'accesso
amministratore si chiude a parte, dalla stessa scheda). Mentre è
sospeso l'installatore vede solo se l'impianto è acceso, e nessuna verifica viene eseguita.
Per scollegare del tutto l'impianto basta arrestare o disinstallare l'add-on.
