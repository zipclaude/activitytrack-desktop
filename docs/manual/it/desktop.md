Versione 0.9.4-beta1 (novembre 2026). ActivityTrack Desktop è l'app per il PC
di ActivityTrack. Sta nell'area di notifica, vicino all'orologio, e tiene a un
clic le attività in corso e i *Da fare*. Così un'attività, anche breve, si
registra dalla tastiera, senza prendere il telefono.

## 1. Cosa serve

- Un server **ActivityTrack Web** dell'organizzazione: il PC si associa come
  un telefono e sincronizza nei due sensi.
- **Linux** con KDE Plasma o XFCE, su Wayland o X11, oppure **Windows 10 o 11**.

Senza rete il PC continua a lavorare: le modifiche partono quando la rete
torna. Report, anagrafiche e gestionali restano al telefono e al web.

## 2. Installazione

Dalla pagina delle release
(<https://github.com/zipclaude/activitytrack-desktop/releases>):

- **Debian 13 e 14, Ubuntu 24.04 e 26.04**: il pacchetto della propria
  distribuzione, installato con
  `sudo apt install ./activitytrack-desktop_<versione>-<distro>_all.deb`.
  ActivityTrack compare nel menu delle applicazioni.
- **Altre distribuzioni Linux**: servono Python 3.11 o più recente, PyQt6,
  cryptography e keyring dai pacchetti della distribuzione. Si scompatta
  `activitytrack-desktop-<versione>.tar.gz` e, nella sua cartella, si avvia
  `python3 -m activitytrack_desktop`.
- **Windows**: `ActivityTrackDesktop-<versione>-setup.exe`. Si installa per
  l'utente corrente, senza diritti di amministratore. Il programma **non è
  firmato** (non ha costi di certificati): al primo avvio Windows SmartScreen
  avvisa; si sceglie **"Ulteriori informazioni" → "Esegui comunque"**. Chi
  vuole controllare il file confronta il suo SHA-256 con `SHA256SUMS` della
  stessa release.

Su XFCE l'icona compare se il pannello ha l'**area di notifica** (plugin
"Status Tray" o "Notification Area"). GNOME senza l'estensione AppIndicator
non ha un'area di notifica: ActivityTrack resta allora aperto in una finestra.

## 3. Associazione al server

![Associazione](../img/pair.png)

1. Sul web, apri **Dispositivi → "Associa un dispositivo"** (su ActivityTrack
   Web 0.9.3: **Telefoni → "Associa un telefono"**, il collegamento è sotto
   "Non riesci a inquadrarlo?").
2. Copia il **collegamento** che inizia con `activitytrack://pair`.
3. Al primo avvio ActivityTrack apre la finestra di associazione: se il
   collegamento è già negli appunti lo trova da solo. Scegli **"Associa"**.

Il collegamento vale 10 minuti e una volta sola. Dopo l'associazione il PC
scarica i dati dell'utente e li tiene aggiornati.

![Sincronizzazione](../img/sync.png)

La scheda **Sincronizzazione** mostra server, utente, organizzazione, le
modifiche in attesa e quelle rifiutate dal server (**"Non sincronizzati"**),
con **"Sincronizza ora"**, **"Associa di nuovo…"** e **"Dissocia"**. Dissociando
il PC tiene i suoi dati; associandolo a un altro server o utente li riparte
da zero.

Il token di accesso sta nel portachiavi del sistema (KWallet, GNOME Keyring,
Gestione credenziali di Windows). Senza portachiavi sta in un file leggibile
solo dal proprio utente, e la scheda lo dice.

## 4. L'icona e il menu

L'icona prende il colore dell'attività in corso: **verde** al lavoro,
**gialla** in pausa, **blu** in viaggio, grigia quando non c'è niente. Un
**punto rosso** dice che la sincronizzazione ha un problema (non associato,
associazione revocata, versioni incompatibili).

- **Passandoci sopra**: le attività in corso con il tempo trascorso.
- **Clic**: apre o chiude la finestra.
- **Clic centrale**: mette in pausa o riprende l'attività al lavoro.
- **Menu** (clic destro): per ogni attività in corso i suoi comandi
  (Pausa, Viaggio, Sospendi, Stop, Modifica…); **"Nuova attività…"**;
  **"Avvia Da fare ▸"** con quelli in ritardo e di oggi; **"Nuovo Da fare…"**;
  lo stato della sincronizzazione; **"Esci"**.

Chiudere la finestra la nasconde soltanto: ActivityTrack resta nell'area di
notifica fino a **"Esci"**.

## 5. Le attività

![La Home](../img/home.png)

### Nuova attività

![Nuova attività](../img/quick.png)

**"Nuova attività…"** (dal menu o dalla finestra) apre l'inserimento rapido,
sopra le altre finestre:

- **Descrizione** su più righe;
- **Cliente**: si sceglie dall'elenco o si scrive. Un nome nuovo diventa
  un'anagrafica personale, se la policy lo consente;
- **Tag**, separati da virgole;
- **Lavoro** o **Viaggio**;
- **"Già fatta"**: un'attività finita, con inizio e fine;
- le **attività in corso**: lasciarle in corso, sospenderle o fermarle.

**Ctrl+Invio** avvia. **"Altri campi…"** passa al modulo completo con quanto
già scritto.

### Il modulo completo

![Modulo completo](../img/entry.png)

Azienda, cliente, ruolo, scelta rapida, descrizione, località, note e tag,
secondo la policy (che può rinominarli, nasconderli o renderli obbligatori).
Per un'attività esistente mostra anche i **tempi**: ogni tratto (lavoro,
viaggio, pausa) si può modificare o eliminare, e se ne aggiunge uno nuovo,
quando la policy lo permette. Due tratti sovrapposti segnano l'attività
**"da verificare"**.

### Stop e completamento

**Stop** chiude subito l'attività se ha cliente e descrizione. Altrimenti, o
se viene da un *Da fare*, chiede quello che manca:

![Completa l'attività](../img/stop.png)

**"Chiudi l'attività"** la completa (senza descrizione chiede conferma);
**"Più tardi"** la lascia tra i **"Dettagli mancanti"** della Home.

## 6. I Da fare

Sotto le attività in corso la Home ha un'unica lista, come l'app: **In
ritardo**, **Dettagli mancanti**, **Oggi**, **Prossimi giorni**, **Giorni
precedenti**, **Senza data**, **Ignorate**. I filtri **periodo**, **stato**,
**azienda** e **tag** restano memorizzati.

Ogni *Da fare* ha **Avvia** (un'attività con i suoi dati), **Fatto** e, nel
menu **⋯**, **Posticipa**, **Ignora** e **Modifica…**.

![Da fare](../img/todo.png)

Il modulo ha titolo, azienda, cliente, note, riferimenti (ticket, link: uno
per riga), **scadenza**, **pianificazione** (giorno, ora, durata) e
**priorità**. Un *Da fare* del gestionale non si elimina: si ignora.

## 7. I promemoria

Gli stessi del telefono, come **notifiche** del desktop:

- **"Ancora su …?"** mentre un'attività è in corso: Sì, Pausa, Stop all'ora
  dell'ultima conferma;
- **"Ancora in pausa?"**: Riprendi, Stop;
- **"Nessuna attività oggi"** dopo l'inizio dell'orario di lavoro: Assente
  tutto il giorno, Avvia un'attività;
- un **Da fare pianificato** in arrivo: Avvia, Posticipa, Ripianifica;
- la **fine prevista** di un'attività: Sì, stop; No, continua.

Su Linux le notifiche hanno i pulsanti. Su Windows, o dove le notifiche non
li hanno, un clic apre la domanda in una finestra:

![Una domanda](../img/question.png)

![Promemoria](../img/reminders.png)

La scheda **Promemoria** accende o spegne ciascuno e ne regola gli intervalli;
quelli fissati dalla policy sono grigi. Il telefono mostra gli stessi
promemoria: una risposta che cambia l'attività o il *Da fare* vale anche
sull'altro dispositivo.

## 8. Generale

La scheda **Generale** ha:

- **"Avvia ActivityTrack all'accesso"**: parte con la sessione, nascosto
  nell'area di notifica. Su Linux si accende al primo avvio; su Windows lo
  propone l'installazione;
- **aggiornamenti**: una volta al giorno ActivityTrack controlla su GitHub se
  c'è una versione nuova, e la notifica con **"Scarica"**. **"Anche le
  versioni beta"** include le versioni di prova. La policy può fissare
  entrambe le scelte.

## 9. La policy sul PC

Il PC riceve la stessa policy del telefono e applica le chiavi che lo
riguardano: funzioni (attività, viaggi, Da fare, pianificazione, ignorare ed
eliminare), campi (nomi, obbligatori, nascosti, sola lettura), tempi
modificabili, tag liberi, attività solo dai *Da fare*, anagrafiche solo
centrali, intervalli dei promemoria, aggiornamenti. Le chiavi solo del
telefono (posizione, chiamate, widget…) non lo riguardano.

## 10. Problemi comuni

| Problema | Cosa fare |
|---|---|
| L'icona non si vede | XFCE: aggiungi al pannello l'area di notifica. GNOME: serve l'estensione AppIndicator |
| Windows: "Windows ha protetto il PC" | Il programma non è firmato: "Ulteriori informazioni" → "Esegui comunque" |
| "Codice scaduto o già usato" | Il collegamento vale 10 minuti e una volta: creane un altro sul web |
| "Il certificato del server non è valido" | Il server ha un certificato autofirmato: usa il collegamento appena creato, che contiene la sua chiave |
| "Il server ha revocato l'associazione" | Associa di nuovo il PC dal web: i dati restano |
| "Il server non accetta più questa versione" | Aggiorna ActivityTrack Desktop (scheda Generale, "Controlla ora") |
| "Va aggiornato il server" | Avvisa l'amministratore di ActivityTrack Web |
| Un'attività fatta sul telefono non compare | Arriva entro 30 secondi; "Sincronizza ora" la porta subito |
