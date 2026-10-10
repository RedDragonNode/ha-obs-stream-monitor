# Spielpartner Recorder

Schreibt die RTSP-Streams der Kameras **ohne Neukodierung** (ffmpeg `-c copy`) in Dateien. Gesteuert wird das Add-on
von der Integration *Spielpartner Aufnahme* (Modus „Recorder" oder „Beide"). Das Add-on selbst hat keine Oberflaeche.

## Einrichtung
1. Ordner `addon/spielpartner_recorder` aus dem Repository nach `/addons/spielpartner_recorder` auf dem HA-Server kopieren
   (Samba-Freigabe `addons`).
2. *Einstellungen → Add-ons → Add-on-Store → ⋮ → Nach Updates suchen* → „Spielpartner Recorder" installieren.
3. Unter *Konfiguration* einen **api_key** setzen (mindestens 12 Zeichen, frei waehlbar) und starten.
4. In der Integration unter *Einstellungen → Recorder* Adresse `http://local-spielpartner-recorder:8099` und denselben
   Schluessel eintragen.

## Einstellungen
| Option | Bedeutung |
| --- | --- |
| `api_key` | Zugangsschluessel zwischen Integration und Add-on |
| `aufnahme_ordner` | Zielordner (Standard `/media/aufnahmen` = Medien-Ordner von HA, z. B. die externe SSD) |
| `container` | `mp4` (fragmentiert, absturzsicher) oder `mkv` |
| `audio` | `aac` (G.711 der Kamera wird nach AAC umgewandelt, minimale Last), `copy`, `none` |
| `stillstand_sekunden` | Wenn so lange keine Daten geschrieben werden, wird die Kamera neu verbunden (neue Datei „… Teil 2") |
| `mindest_frei_gb` | Start wird verweigert / Aufnahme beendet, wenn weniger Platz frei ist |
| `wallclock_zeitstempel` | Nur aktivieren, wenn eine Kamera fehlerhafte Zeitstempel liefert |
| `video_tag` | `hvc1` setzt HEVC in MP4 so, dass Windows/Apple-Player es abspielen |

## Dateien
Pro Sitzung entsteht neben den Videos eine `<Sitzung>.json` mit Start/Ende jeder Kamera und jedes Teils (UTC) –
damit lassen sich die Kameras spaeter zeitgenau synchronisieren.
