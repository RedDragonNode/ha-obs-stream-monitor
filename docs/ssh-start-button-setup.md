# "OBS starten"-Button einrichten (SSH)

Optionale Funktion von OBS Stream Monitor: ein Button in Home Assistant, der OBS auf dem
Windows-Rechner startet, auch wenn es gerade nicht läuft. Da obs-websocket nur mit einem
bereits laufenden OBS sprechen kann, läuft das über eine SSH-Verbindung zu Windows, die
dort eine Scheduled Task auslöst.

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
stillschweigend verworfen (Symptom: Button-Fehler "timed out", obwohl SSH korrekt läuft).

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

## 3. Scheduled Task anlegen (einmal pro OBS-Installation)

**Aufgabenplanung** öffnen (Win-Taste → "Aufgabenplanung", oder `taskschd.msc`) →
**Aufgabenplanungsbibliothek** → rechts **"Aufgabe erstellen..."** (nicht "Einfache Aufgabe
erstellen" - der hat nicht alle nötigen Optionen).

- **Reiter "Allgemein":**
  - Name, z. B. `StartOBS` (muss später 1:1 ins HA-Feld "Name der Scheduled Task")
  - **"Nur ausführen, wenn der Benutzer angemeldet ist"** auswählen (wichtig! Die
    Alternative "Unabhängig von der Benutzeranmeldung" startet OBS unsichtbar in einer
    eigenen Session statt auf dem echten Desktop)
- **Reiter "Trigger":** leer lassen - die Aufgabe wird nur per `schtasks /run` von Home
  Assistant aus ferngestartet, braucht keinen eigenen Zeitplan
- **Reiter "Aktionen" → Neu...:**
  - **Programm/Skript:** Pfad zur exe, die du sonst auch per Doppelklick startest
    (z. B. `...\bin\64bit\obs64.exe` bei einer Portable-Installation)
  - **Starten in (optional):** der Ordner, in dem diese exe liegt - **nicht leer lassen**,
    sonst findet eine Portable-Installation ihre lokale Config nicht

Mit OK bestätigen (zwei Dialoge).

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
SSH-Port (Standard `22`), Name der Scheduled Task (aus Schritt 3) eintragen. Der
"OBS starten"-Button erscheint danach automatisch, kein Neustart nötig.

## Verbindung manuell testen

Am schnellsten lässt sich ein Auth-Problem von einem HA-SSH-Problem unterscheiden, indem
man direkt aus dem Terminal/SSH-Add-on von Home Assistant testet:

```
ssh BENUTZERNAME@IP-DES-RECHNERS
```

- Scheitert das genauso → Problem liegt auf Windows-Seite (Schritt 1-4 prüfen)
- Klappt das, aber der HA-Button meldet trotzdem einen Fehler → Tippfehler in den
  HA-Optionsfeldern (Leerzeichen, Sonderzeichen)

## Fehlermeldungen und was sie bedeuten

| Meldung im HA-Button-Fehler | Ursache | Lösung |
|---|---|---|
| `timed out` | SSH-Pakete kommen nicht an (meist Firewall/Netzwerkprofil) | Schritt 2 |
| `Authentication failed` | Benutzername/Passwort falsch, bei Microsoft-Konto nur Kurzname statt voller E-Mail-Adresse verwendet, oder Passwort-Login für das Konto blockiert | Schritt 4 |
| Button lässt sich gar nicht drücken / fehlt | Integration vor v0.2.1: komplette Einrichtung scheiterte, wenn OBS beim Laden nicht erreichbar war | Auf v0.2.1 oder neuer aktualisieren |
| `schtasks meldete Exit-Code ...` | Task-Name in HA stimmt nicht exakt mit dem Namen in der Aufgabenplanung überein | Schritt 3 - Name 1:1 abgleichen |

## Mehrere OBS-Installationen (nacheinander genutzt)

Siehe Haupt-README, Abschnitt zu mehreren Instanzen: jede Installation bekommt einen
eigenen WebSocket-Port (auch wenn nie gleichzeitig genutzt) plus eine eigene Scheduled
Task, dann in HA zwei getrennte Integrationseinträge mit jeweils eigenem Task-Namen in den
Optionen.
