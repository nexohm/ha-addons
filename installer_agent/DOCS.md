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

## Sospendere l'accesso

Dal pannello **Assistenza** puoi sospendere l'accesso remoto in qualsiasi momento. Mentre è
sospeso l'installatore vede solo se l'impianto è acceso, e nessuna verifica viene eseguita.
Per scollegare del tutto l'impianto basta arrestare o disinstallare l'add-on.
