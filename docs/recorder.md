# Recorder: Aufnahme direkt vom Kamera-Stream

Ersetzt OBS „Source Record“. Der HA-Server schreibt den RTSP-Stream jeder Kamera **ohne Neukodierung**
(ffmpeg `-c copy`) in eine Datei. Keine GPU, kaum CPU, OBS macht nur noch die Live-Szene.

```
Integration (Steuerung)  ──HTTP──▶  Add-on „Spielpartner Recorder“  ──ffmpeg-copy──▶  Kamera (RTSP)
 Cams, Kürzel, Zähler,              pro Cam ein ffmpeg, Neustart,                      │
 Dateinamen, Discord                Stillstandserkennung, Sidecar                      ▼
                                                                         /media/aufnahmen/Spielen mit …/Saison …/
```

## 1. Speicher (externe SSD)

Auf dem HA-Server (SSH, erst **nach** dem Kopieren der alten Daten – formatieren löscht alles):

```bash
lsblk -f                                   # SSD finden, z. B. sda
sudo parted /dev/sda --script mklabel gpt mkpart aufnahmen ext4 0% 100%
sudo mkfs.ext4 -L aufnahmen /dev/sda1
sudo mkdir -p /usr/share/hassio/media/aufnahmen
echo 'LABEL=aufnahmen /usr/share/hassio/media/aufnahmen ext4 defaults,nofail 0 2' | sudo tee -a /etc/fstab
sudo mount -a && sudo reboot
```

`nofail` verhindert, dass der Server ohne SSD nicht mehr startet. Ohne eingehängte SSD würde das Add-on auf die
Systemplatte schreiben – `mindest_frei_gb` schützt davor (Start wird verweigert).
Richtwert: 5 Cams in 4K ≈ 18–36 GB pro Stunde.

## 2. Add-on

1. Ordner `addon/spielpartner_recorder` auf den Server nach `/addons/spielpartner_recorder` kopieren (Samba-Freigabe `addons`).
2. *Einstellungen → Add-ons → Add-on-Store → ⋮ → Nach Updates suchen* → **Spielpartner Recorder** installieren.
3. Unter *Konfiguration* einen `api_key` setzen (mind. 12 Zeichen), starten.

Optionen siehe `addon/spielpartner_recorder/DOCS.md`. Standard: fragmentiertes MP4 (absturzsicher, auch bei Stromausfall
nur die letzte Sekunde verloren), Audio G.711 → AAC, Neustart nach 20 s ohne Daten.

## 3. Integration

*Konfigurieren* der Integration:

| Einstellung | Wert |
|---|---|
| Modus | `recorder` (nur Recorder), `beide` (OBS + Recorder zum Vergleichen) oder `obs` (wie bisher) |
| Recorder-Adresse | `http://local-spielpartner-recorder:8099` |
| Recorder-Schlüssel | derselbe `api_key` wie im Add-on |
| Recorder startet/stoppt mit der OBS-Aufnahme | an = Aufnahme-Entity von OBS steuert den Recorder (gewohnter Ablauf) |

Pro **Cam** (Cam bearbeiten): *Recorder: diese Cam aufnehmen*, und **entweder** *Stream-Quelle über eine HA-Kamera*
(z. B. die Reolink-Kamera, HA liefert die RTSP-Adresse) **oder** *direkte RTSP-Adresse* (hat Vorrang).
Tipp: den **Hauptstream** (volle Auflösung) verwenden, nicht den Substream.

## Ablauf

1. **Aufnahme vorbereiten** – legt Ordner über den Recorder an, erkennt neue Saison, Discord-Thread wie gehabt.
2. **Recorder starten** (Button, Service `recorder_starten`, oder automatisch mit OBS) – pro Cam eine Datei
   `#01.02.03.FB.14 (4K) 10.10.2026.mp4` (Datum bereits aufgelöst).
3. Nach *x* Minuten: Discord-Statusbeitrag wie bisher.
4. **Recorder stoppen** – Dateien werden sauber abgeschlossen, die Aufnahme wird **einmal** gezählt.

Bricht eine Kamera ab, verbindet der Recorder neu und schreibt in `… Teil 2.mp4`. Beendet das Add-on die Aufnahme
selbst (Platte fast voll, Add-on-Neustart), meldet die Integration das mit Grund und zählt trotzdem einmal.
Nach einem HA-Neustart verbindet sich die Integration wieder mit der laufenden Aufnahme.

## Dateien & Synchronisation

Neben den Videos liegt `#01.02.03 Sitzung.json` (Start/Ende je Cam und Teil in UTC). Fuer den Schnitt
lassen sich die Kameras damit zeitgenau ausrichten. Ein-/Ausschaltverzoegerungen von wenigen Sekunden zwischen den
Cams sind normal (RTSP-Verbindungsaufbau).

## Entities

Hub: *Recorder erreichbar*, *Recorder nimmt auf*, *freier Speicher*, Buttons *Recorder starten/stoppen*.
Pro Cam: *Aufnahme* (Status, Datei, Teil, Neustarts, Größe, letzter Fehler).

## Sicherheit

Das Add-on ist nur im internen Home-Assistant-Netz erreichbar (kein veröffentlichter Port) und verlangt den
`api_key`. Zugangsdaten in RTSP-Adressen werden in Logs und Status maskiert. Pfade werden bereinigt;
Ordner außerhalb von `aufnahme_ordner` sind nicht erreichbar.
