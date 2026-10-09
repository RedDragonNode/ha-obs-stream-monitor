# "OBS"-Schalter einrichten (SSH)

Optionale Funktion von OBS Stream Monitor: ein Schalter in Home Assistant, der OBS auf dem
Windows-Rechner startet, auch wenn es gerade nicht läuft - und beim Ausschalten OBS wieder
**sanft beendet** (nicht hart abgewürgt). Da obs-websocket nur mit einem bereits laufenden
OBS sprechen kann, läuft beides über eine SSH-Verbindung zu Windows.

**Wichtig ab v0.7.5 (betrifft alle, die den Schalter schon eingerichtet hatten):** Das
Ausschalten brauchte bis v0.7.4 keine eigene Scheduled Task - lief aber deshalb direkt über
die SSH-Sitzung, und genau das stellte sich als grundsätzlich unzuverlässig heraus: Eine
SSH-Sitzung läuft in einer eigenen, nicht-interaktiven Windows-Sitzung und kann die Fenster
von OBS auf dem echten Desktop schlicht nicht sehen - unabhängig davon, ob OBS im Tray
minimiert oder "als Administrator" gestartet ist. Seit v0.7.5 braucht das Ausschalten
**ebenfalls eine eigene Scheduled Task** (Schritt 3 unten) - ohne sie bleibt der Schalter
zum Ausschalten mit einer klaren Fehlermeldung ("task does not exist") stehen, bis sie
angelegt ist. Einschalten ist davon nicht betroffen.

Alles unten ist **einmalig** auf dem Rechner einzurichten, auf dem OBS läuft.

## 1. OpenSSH-Server aktivieren

**Einstellungen → System → Optionale Features** (bei älteren Windows-Builds unter
**Apps → Optionale Features**) → **Feature hinzufügen** → nach "OpenSSH" suchen →
**OpenSSH-Server** installieren.

Danach in einer **administrativen** PowerShell:

```powershell
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
Get-Service sshd
```

Die letzte Zeile muss `Status: Running` zeigen.

## 2. Netzwerkprofil auf "Privat" stellen

**Das ist der Schritt, der am leichtesten übersehen wird.** Die OpenSSH-Installation legt
zwar automatisch eine Firewall-Regel an, die aber nur fürs **Private**-Netzwerkprofil gilt.
Läuft die Verbindung im "Öffentlichen Netzwerk"-Profil, werden eingehende SSH-Verbindungen
stillschweigend verworfen (Symptom: Schalter-Fehler "timed out", obwohl SSH korrekt läuft).

**Einstellungen → Netzwerk und Internet → Ethernet** (bzw. WLAN) → **Netzwerkprofiltyp**
von "Öffentliches Netzwerk" auf **"Privates Netzwerk"** umstellen.

Zur Kontrolle, ob die Firewall-Regel existiert und für welches Profil sie gilt:

```powershell
Get-NetFirewallRule -DisplayName "*ssh*" | Select DisplayName, Enabled, Direction, Action, Profile
```

Sollte `Enabled: True`, `Direction: Inbound`, `Action: Allow` zeigen. Fehlt die Regel komplett:

```powershell
New-NetFirewallRule -DisplayName "OpenSSH SSH Server (sshd)" -Direction Inbound -Protocol TCP -LocalPort 22 -Action Allow
```

## 3. Scheduled Tasks anlegen (je zwei pro OBS-Installation: Starten + Beenden)

Beide brauchen dieselbe Grundeinstellung - laufen nur per Fernstart von Home Assistant aus,
nie nach Zeitplan - und müssen **in der angemeldeten Sitzung** laufen, nicht "unabhängig von
der Benutzeranmeldung": nur so landen sie auf dem echten, sichtbaren Desktop statt in einer
unsichtbaren Extra-Sitzung, in der sie OBS weder zeigen noch dessen Fenster finden können.

**Aufgabenplanung** öffnen (Win-Taste → "Aufgabenplanung", oder `taskschd.msc`) →
**Aufgabenplanungsbibliothek** → rechts **"Aufgabe erstellen..."** (nicht "Einfache Aufgabe
erstellen" - der hat nicht alle nötigen Optionen).

### 3a. Task zum Starten

- **Reiter "Allgemein":**
  - Name, z. B. `StartOBS` (muss später 1:1 ins HA-Feld "Name der Scheduled Task (Starten)")
  - **"Nur ausführen, wenn der Benutzer angemeldet ist"** auswählen (wichtig! Die
    Alternative "Unabhängig von der Benutzeranmeldung" startet OBS unsichtbar in einer
    eigenen Session statt auf dem echten Desktop)
- **Reiter "Trigger":** leer lassen
- **Reiter "Aktionen" → Neu...:**
  - **Programm/Skript:** Pfad zur exe, die du sonst auch per Doppelklick startest
    (z. B. `...\bin\64bit\obs64.exe` bei einer Portable-Installation)
  - **Starten in (optional):** der Ordner, in dem diese exe liegt - **nicht leer lassen**,
    sonst findet eine Portable-Installation ihre lokale Config nicht

Mit OK bestätigen (zwei Dialoge).

### 3b. Task zum Beenden (neu ab v0.7.5)

Braucht zuerst eine kleine Skriptdatei auf dem Windows-Rechner - die eigentliche
"OBS sanft schließen"-Logik (sucht alle echten Fenster von OBS, auch ein gerade in den
System-Tray minimiertes, und schickt jedem ein normales Schließen-Signal `WM_CLOSE`, **kein**
hartes Abwürgen):

1. Datei **`stop-obs.ps1`** aus dem Repo-Zip (Ordner `windows-scripts/`) irgendwohin auf den
   Windows-Rechner kopieren, z. B. direkt neben die OBS-exe oder nach
   `C:\Users\DEIN-BENUTZER\obs-stream-monitor\stop-obs.ps1`. Der genaue Ort ist egal - er
   wird gleich im nächsten Schritt als Pfad eingetragen.
2. Datei mit einem Texteditor öffnen und ganz oben die Zeile `$ProcessName = 'obs64'` prüfen
   - bei einer normalen 64-Bit-Installation passt das bereits; bei einer 32-Bit-Installation
   oder einem umbenannten Build hier den tatsächlichen Namen eintragen, **ohne** `.exe`
   (genau wie im Task-Manager, Reiter "Details", Spalte "Name", nur ohne die Endung).

Dann die zweite Aufgabe anlegen:

- **Reiter "Allgemein":**
  - Name, z. B. `StopOBS` (muss später 1:1 ins HA-Feld "Name der Scheduled Task (Beenden)")
  - **"Nur ausführen, wenn der Benutzer angemeldet ist"** auswählen (genau wie bei 3a - das
    ist hier sogar der ganze Witz der eigenen Task, siehe die Erklärung oben)
- **Reiter "Trigger":** leer lassen
- **Reiter "Aktionen" → Neu...:**
  - **Programm/Skript:** `powershell.exe`
  - **Argumente hinzufügen (optional):**
    `-NoProfile -ExecutionPolicy Bypass -File "C:\Pfad\zu\stop-obs.ps1"` (den Pfad aus
    Schritt 1 oben einsetzen, in Anführungszeichen)

Mit OK bestätigen (zwei Dialoge). Ein Lauf schreibt sein Ergebnis zusätzlich in eine
`stop-obs.log`-Datei direkt neben dem Skript - praktisch, falls der Schalter mal nicht
reagiert und die Aufgabenplanung selbst (Verlauf-Reiter der Task) nicht genug Detail zeigt.

## 4. SSH-Zugangsdaten besorgen

Passwort ist dein ganz normales Windows-Login-Passwort, kein Extra-Account. Beim
Benutzernamen kommt es drauf an, mit was für einem Konto du angemeldet bist:

- **Lokales Konto:** siehe Task-Scheduler-Dialog, Feld "Autor" (z. B. `RECHNERNAME\the-d` →
  der Teil nach dem Backslash)
- **Microsoft-Konto:** hier reicht der Teil nach dem Backslash aus dem Task-Scheduler
  **nicht** - als SSH-Benutzername muss die **volle E-Mail-Adresse** des Microsoft-Kontos
  rein (z. B. `the-dragon-88@web.de`), sonst schlägt die Anmeldung fehl, selbst wenn
  Passwort und alles andere stimmen.

**Bei einem Microsoft-Konto zusätzlich prüfen:** Unter **Einstellungen → Konten →
Anmeldeoptionen** ganz unten, ob **"Für Microsoft-Konten auf diesem Gerät aus
Sicherheitsgründen nur Anmeldung mit Windows Hello erlauben"** aktiviert ist. Wenn ja,
**ausschalten** - sonst lehnt Windows jede Passwort-Anmeldung ab (SSH meldet
"Authentication failed", obwohl das Passwort stimmt), weil nur noch PIN/Windows Hello als
Login erlaubt ist. Das SSH-Passwort ist dann das normale Passwort des Microsoft-Kontos,
nicht die PIN.

## 5. In Home Assistant eintragen

Integration **OBS Stream Monitor** → **Konfigurieren** → SSH-Benutzername, SSH-Passwort,
SSH-Port (Standard `22`), Name der Scheduled Task (Starten) (aus Schritt 3a) und Name der
Scheduled Task (Beenden) (aus Schritt 3b) eintragen. Der **"OBS"-Schalter** erscheint
danach automatisch, kein Neustart nötig.

### Wie der Schalter funktioniert

- **Einschalten:** löst die Scheduled Task aus Schritt 3a aus - wie bisher.
- **Ausschalten:** löst die Scheduled Task aus Schritt 3b aus, die wiederum `stop-obs.ps1`
  ausführt: sucht alle echten Fenster (mit Titelleiste) von OBS - auch ein gerade in den
  System-Tray minimiertes - und schickt jedem ein ganz normales Schließen-Signal
  (`WM_CLOSE`), **kein** hartes Abwürgen. OBS läuft also seine normale Beenden-Routine
  durch (laufende Aufnahme sauber abschließen, bei aktivem Stream/Aufnahme ggf. mit
  Bestätigungsnachfrage), genau wie bei einem Klick auf das eigene Schließen-Symbol.

  (Frühere Versionen haben dafür erst `taskkill` ohne `/F` benutzt - das lehnt Windows
  bei OBS und vielen anderen gewöhnlichen GUI-Programmen aber grundsätzlich ab, mit der
  Meldung "Dieser Prozess kann nur zwangsweise beendet werden (mit der Option /F)" - und
  danach .NETs `CloseMainWindow()` (ab v0.6.1), das wiederum ein minimiert-im-Tray
  laufendes OBS gar nicht erst als "Hauptfenster" erkannt hat. v0.6.2 bis v0.7.4 liefen
  dafür direkt über die Windows-Fenster-API, aber noch innerhalb der SSH-Sitzung selbst -
  die kann OBS' Fenster grundsätzlich nicht sehen, unabhängig von Tray-Status oder
  Adminrechten (siehe Hinweis ganz oben). Seit v0.7.5 läuft genau dieselbe Fenster-API-Logik
  stattdessen als eigene Scheduled Task (Schritt 3b) in der echten, sichtbaren Sitzung.)

  **Läuft gerade ein Stream oder eine Aufnahme**, zeigt OBS dafür einen
  Bestätigungsdialog **auf dem echten Bildschirm** des Windows-Rechners (dieselbe
  interaktive Sitzung, in der auch die Scheduled Task läuft) - der muss dann von Hand
  weggeklickt werden, ferngesteuert geht das nicht. Um das zu vermeiden: vor dem
  Ausschalten erst Stream/Aufnahme über die neuen "Stream"/"Aufnahme"-Schalter stoppen
  (siehe Haupt-README, Abschnitt "OBS-Steuerung").

Der Schalter-Zustand selbst (an/aus) zeigt, ob OBS laut letzter Abfrage erreichbar ist -
genau wie der neue Sensor "OBS läuft". Er bleibt dabei bewusst **immer bedienbar**, auch
wenn OBS gerade nicht läuft (anders als z. B. die Stream-/Aufnahme-Schalter) - sonst könnte
man OBS ja nie aus dem Aus-Zustand heraus wieder starten.

## Verbindung manuell testen

Am schnellsten lässt sich ein Auth-Problem von einem HA-SSH-Problem unterscheiden, indem
man direkt aus dem Terminal/SSH-Add-on von Home Assistant testet:

```
ssh BENUTZERNAME@IP-DES-RECHNERS
```

- Scheitert das genauso → Problem liegt auf Windows-Seite (Schritt 1-4 prüfen)
- Klappt das, aber der HA-Schalter meldet trotzdem einen Fehler → Tippfehler in den
  HA-Optionsfeldern (Leerzeichen, Sonderzeichen)

## Sonderfall: Grundverbindung (Port 4455) bricht, obwohl SSH/der "OBS"-Schalter funktioniert

Das betrifft nicht den SSH-Schalter selbst, sondern die normale, immer aktive
**Grundverbindung** der Integration (obs-websocket, Standardport `4455`) - die braucht gar
kein SSH und läuft unabhängig davon. Fällt sie aus, gehen alle Sensoren und
Steuer-Entitäten auf "nicht verfügbar"/"aus" (inkl. "OBS läuft"), **obwohl** SSH (Port 22)
und damit der "OBS"-Schalter zum Starten/Beenden weiterhin klaglos funktionieren - diese
Kombination ist das Erkennungsmerkmal für genau dieses Problem. In den
Home-Assistant-Logs (Einstellungen → System → Protokolle, oder `ha_get_logs`/MCP):
wiederholte `TimeoutError`/`WebSocketTimeoutException` beim Verbindungsaufbau zu
`HOST:4455`, mal beim `connect()`, mal beim Warten auf die erste Antwort - beides dieselbe
Ursache.

**Ursache bei einem portablen OBS auf einem externen/Wechsel-Laufwerk:** Windows weist so
einem Laufwerk nicht garantiert jedes Mal denselben Buchstaben zu. Programmbasierte
Firewall-Regeln für `obs64.exe`/"OBS Studio" hängen aber am exakten Dateipfad inklusive
Laufwerksbuchstabe - über Monate sammeln sich so viele alte, nicht mehr zutreffende Regeln
an (`S:\...`, `V:\...`, `X:\...`, `D:\...` etc.), während die *aktuell* laufende Instanz
keine zuverlässig passende Regel mehr trifft. Windows verwirft eingehende Verbindungen für
sie dann still (kein "Connection refused" - einfach "timed out", die Pakete kommen nie an),
und das selbst dann, wenn OBS selbst nachweislich korrekt auf `0.0.0.0:4455` lauscht und das
Netzwerkprofil "Privat" ist (Schritt 2 oben) - also trotz vermeintlich korrekter
Grundkonfiguration.

**Diagnose, in dieser Reihenfolge:**

```powershell
# 1. Lauscht OBS überhaupt nach außen (nicht nur localhost)?
netstat -ano | findstr 4455
# sollte eine Zeile "0.0.0.0:4455   ...   ABHÖREN" zeigen

# 2. Netzwerkprofil wirklich "Private"? (nicht nur die App-Regeln)
Get-NetConnectionProfile

# 3. Welche Pfade deckt die Firewall gerade tatsächlich ab?
Get-NetFirewallRule -DisplayName "*obs*" | Get-NetFirewallApplicationFilter | Select -Unique Program
```

Ein Selbsttest auf die eigene IP (`Test-NetConnection -ComputerName EIGENE-IP -Port 4455`
vom selben Rechner aus) ist dabei **nicht zuverlässig** - Windows kann das intern über
Loopback umleiten, ohne die Firewall für eingehende Verbindungen überhaupt zu durchlaufen.
Echter Test ist nur von einem anderen Gerät im Netz, am besten direkt von Home Assistant
aus (Terminal & SSH-Add-on):

```
curl -v telnet://IP-DES-RECHNERS:4455
```

Hängt das endlos bei "Trying ..." (statt sofort "Connection refused" oder
"Established connection to ..."), ist das die Bestätigung.

**Fix:** Statt den alten pfadbasierten Regeln hinterherzuräumen, eine robuste, vom
Dateipfad unabhängige Regel direkt für den Port anlegen (passt den Laufwerksbuchstaben nie
wieder etwas an):

```powershell
New-NetFirewallRule -DisplayName "OBS WebSocket (4455)" -Direction Inbound -Protocol TCP -LocalPort 4455 -Action Allow -Profile Private
```

(Bei einem anderen als dem Standard-Port - z. B. bei mehreren OBS-Installationen, siehe
unten - die Portnummer entsprechend anpassen.) Danach den `curl`-Test oben wiederholen:
"Established connection to ..." statt endlosem Hängen = behoben. Die Integration holt sich
die nächsten Live-Daten automatisch beim nächsten Poll (max. 10s), ohne Neustart. Die alten,
nicht mehr zutreffenden Pfad-Regeln können aufgeräumt werden, müssen es aber nicht - die
neue Portregel wirkt unabhängig davon.

## Fehlermeldungen und was sie bedeuten

| Meldung im HA-Fehler | Ursache | Lösung |
|---|---|---|
| `timed out` | SSH-Pakete kommen nicht an (meist Firewall/Netzwerkprofil) | Schritt 2 |
| `Authentication failed` | Benutzername/Passwort falsch, bei Microsoft-Konto nur Kurzname statt voller E-Mail-Adresse verwendet, oder Passwort-Login für das Konto blockiert | Schritt 4 |
| Schalter lässt sich gar nicht bedienen / fehlt | Integration vor v0.2.1: komplette Einrichtung scheiterte, wenn OBS beim Laden nicht erreichbar war | Auf v0.2.1 oder neuer aktualisieren |
| `schtasks meldete Exit-Code ...` / `The system cannot find the file specified` oder `... does not exist` (beim Ein- **oder** Ausschalten) | Task-Name in HA stimmt nicht exakt mit dem Namen in der Aufgabenplanung überein - ab v0.7.5 auch beim Ausschalten möglich, wenn die neue Task aus Schritt 3b noch fehlt | Schritt 3a/3b - Namen 1:1 abgleichen; nach einem Update auf v0.7.5 prüfen, ob Schritt 3b schon gemacht wurde |
| `This process can only be terminated forcefully (with /F)` (beim Ausschalten) | Nur in Versionen vor v0.6.1 - benutzten dafür `taskkill`, das diese Einschränkung hat | Aktualisieren |
| `CloseMainWindow fehlgeschlagen ...` (beim Ausschalten) | Nur in v0.6.1: .NETs Heuristik fand OBS' Fenster nicht (z. B. weil OBS im Tray minimiert war) | Aktualisieren |
| `Kein Fenster für den Prozess gefunden ...` (beim Ausschalten) | In v0.6.2-v0.7.4: Die EnumWindows-Logik lief noch direkt in der SSH-Sitzung, die OBS' Fenster strukturell nicht sehen kann (unabhängig von Tray-Status/Adminrechten - siehe Hinweis ganz oben) | Auf v0.7.5 oder neuer aktualisieren **und** Schritt 3b (neue Scheduled Task) nachholen |
| Schalter zum Ausschalten bleibt ohne jede Fehlermeldung wirkungslos (ab v0.7.5) | `stop-obs.ps1` lief zwar (Task ausgelöst), fand aber kein Fenster oder konnte das Signal nicht senden | `stop-obs.log` neben dem Skript öffnen (Schritt 3b) - zeigt den genauen Grund |
| Schalter zeigt nach "Ausschalten" sofort wieder "an" | OBS läuft noch (Beenden-Dialog wartet auf Bestätigung auf dem Bildschirm, siehe oben), oder braucht noch ein paar Sekunden zum Schließen | Am Bildschirm nachsehen; nächste Abfrage (max. 10s) aktualisiert den Zustand |
| Alle Sensoren/Entitäten "nicht verfügbar", "OBS läuft" bleibt aus, aber der "OBS"-Schalter startet/beendet OBS trotzdem anstandslos | Grundverbindung (Port 4455) gestört, unabhängig von SSH - typischerweise verwaiste pfadbasierte Firewall-Regeln bei portablem OBS auf wechselndem Laufwerksbuchstaben | Siehe Abschnitt "Sonderfall: Grundverbindung (Port 4455) bricht ..." oben |

## Mehrere OBS-Installationen (nacheinander genutzt)

Siehe Haupt-README, Abschnitt zu mehreren Instanzen: jede Installation bekommt einen
eigenen WebSocket-Port (auch wenn nie gleichzeitig genutzt) plus ein eigenes Paar
Scheduled Tasks (Starten + Beenden, inklusive eigener Kopie von `stop-obs.ps1`), dann in HA
zwei getrennte Integrationseinträge mit jeweils eigenen Task-Namen in den Optionen.
