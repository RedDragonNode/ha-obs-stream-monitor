<p align="center">
  <img src="custom_components/spielpartner_aufnahme/brand/logo.png" alt="Spielpartner Aufnahme" width="520">
</p>

# Spielpartner Aufnahme

Private Home-Assistant-Integration für **Spielen Spezial**: Spielpartner anlegen und pflegen,
Aufnahmen vorbereiten, Zähler führen, OBS-Dateinamen setzen und Discord-Threads bedienen –
alles an einem Ort, ohne Helfer-Sammlung, Skript und Automationen.

> Privates Repo, MIT-Lizenz. Gebaut für die eigene Integration
> [ha-obs-stream-monitor](https://github.com/RedDragonNode/ha-obs-stream-monitor).

## Was sie ersetzt

| Früher | Jetzt |
|---|---|
| ~10 Helfer pro Spielpartner (Zähler, Ordner, Thread, Kanal-ID, Dateiformat …) | 1 Spielpartner = 1 Eintrag (Gerät) mit 3 Zähler-Zahlen, Pfad-, Format- und Thread-Sensor |
| Skript „Aufnahme Vorbereitung“ (≈ 40 Schritte) | Button „Aufnahme vorbereiten“ oder Service `spielpartner_aufnahme.aufnahme_vorbereiten` |
| Skript „OBS Source Record Dateiformatierung“ (Kürzel nur für FB/HB) | Jede Cam mit eigenem Kürzel als eigener Eintrag |
| Automation „Aufnahme beendet – Zähler hochzählen“ | automatisch (Aufnahme `an → aus`) |
| Automation „Aufnahme läuft 5 Min – Video-ID, Schaukel, Schnappschüsse posten“ | automatisch, Wartezeit einstellbar |
| `rest_command` / `notify` für Discord | direkt in der Integration (Bot-Token) |

## Neu in 0.2.0: Recorder (Aufnahme ohne OBS-Neukodierung)

Die Integration kann die Kameras jetzt selbst aufnehmen: ein Add-on schreibt die RTSP-Streams per Stream-Copy
auf die Platte des HA-Servers – ohne GPU-Last. Modi: `obs` (wie bisher), `recorder`, `beide`.
Einrichtung und Ablauf: [docs/recorder.md](docs/recorder.md).

## Installation

**Manuell:** Ordner `spielpartner_aufnahme` aus dem Archiv nach `config/custom_components/` kopieren
(Ergebnis: `config/custom_components/spielpartner_aufnahme/manifest.json`), Home Assistant neu starten.

**HACS (privates Repo):** HACS → ⋮ → *Benutzerdefinierte Repositories* → Repo-URL, Kategorie *Integration*
(dafür braucht HACS Zugriff auf private Repos, z. B. über ein GitHub-Token).

Danach: *Einstellungen → Geräte & Dienste → Integration hinzufügen → „Spielpartner Aufnahme“*.

## Einrichtung

1. **Grundeinstellungen** (alles später unter *Konfigurieren* änderbar):
   Basis-Pfade, Ordner-Präfix, Dateiname-Endung, Aufnahme-Entity, Wartezeit für den Statusbeitrag,
   optional Discord-Bot-Token, Schaukel-Cover und die Entities des PC-Ordner-Werkzeugs.
   Die Vorgaben entsprechen deinem bisherigen System.
2. Die **16 Standard-Cams** (Bauleitung … Wildspur) werden mit ihrem Kürzel gleich mit angelegt.
3. **Spielpartner hinzufügen** (Drei-Punkte-Menü des Eintrags → *Spielpartner hinzufügen*):
   Kennung, Anzeigename, Ordner-Nummer (`#01`), Discord-Forum-Kanal-ID.
   Die **Startwerte** (Saison, Aufnahmen in Saison, Aufnahmen gesamt) legen fest, mit welchen Zählern der
   Spielpartner beginnt (leer = 1). Sie lassen sich später direkt an den Zahlenfeldern ändern.
4. **Cams bearbeiten**: Kürzel, optional Kamera für Schnappschüsse und das Häkchen **„In Discord posten“**.
   Nur angehakte Cams erscheinen im Discord-Beitrag.

## Ablauf einer Aufnahme

1. **Aufnahme vorbereiten** (Button am Spielpartner-Gerät, Service oder Dashboard-Karte):
   - Ordner `Spielen mit <Name> #<Nr>` wird über das PC-Ordner-Werkzeug angelegt/geöffnet.
   - Existieren schon Saison-Ordner und der heutige fehlt → **neue Saison** (Saison +1, Aufnahmen in Saison auf 1).
   - Ordner `Saison <SS> vom <TT,MM,JJJJ>` wird angelegt.
   - Pfad wird in **alle** Source-Record-Filter geschrieben, der Dateiname mit dem Kürzel der jeweiligen Cam
     in die zugeordneten Filter.
   - Fehlt der Discord-Thread der Saison, wird er im Forum angelegt.
   - Eine Benachrichtigung fasst alles zusammen (inkl. Hinweisen, falls etwas nicht erreichbar war).
2. **Aufnahme läuft x Minuten**: Beitrag im Saison-Thread. Zuerst eine Kopfzeile mit der Schaukel-Position,
   danach **jede angehakte Cam einzeln und zeitlich versetzt** (Abstand einstellbar, Standard 20 Sekunden):
   Schnappschuss, direkt darunter die Video-ID dieser Cam.
3. **Aufnahme endet**: „Aufnahmen in Saison“ und „Gesamt“ steigen um 1, die Dateinamen in OBS
   werden direkt für die nächste Aufnahme aktualisiert.

### Dateiname

```
#<Ordner-Nr>.<Saison>.<Aufnahme in Saison>.<Cam-Kürzel>.<Gesamt><Endung>
#01.02.03.FB.14 (4K) %DD.%MM.%CCYY
```

Alle Zahlen zweistellig. Die Endung ist einstellbar. Das Sensor-Gerät jeder Cam zeigt ihren aktuellen Dateinamen.

### Welche OBS-Filter gehören zu welcher Cam?

Automatisch über den **Namen**: Enthält Quelle oder Entity-ID des Source-Record-Filters den Cam-Namen
(Umlaute aufgelöst, z. B. `Hoelenblick`), gehört der Filter zur Cam. Filter ohne zugeordnete Cam bekommen den
Pfad, aber keinen Dateinamen – die Benachrichtigung nennt sie.

> **Wichtig:** Das alte Skript und die alten Automationen (Zähler hochzählen, 5-Minuten-Post) schreiben mit
> ihren alten Zählern ebenfalls Dateinamen in OBS und überschreiben die der Integration. Sie müssen
> ausgeschaltet sein, sobald die Integration übernimmt.

## Entities

Pro Spielpartner (eigenes Gerät): Zähler **Saison**, **Aufnahmen in Saison**, **Aufnahmen gesamt**
(Zahlenfelder, direkt editierbar), Sensoren **Speicher-Adresse**, **Dateiformat**, **Discord-Thread**
und der Button **Aufnahme vorbereiten**. Pro Cam: Sensor **Dateiformat**. Global: **Aktueller Spielpartner**
(mit Zählern als Attribute) und **Status**.

## Services

| Service | Zweck |
|---|---|
| `spielpartner_aufnahme.aufnahme_vorbereiten` | wie der Button; liefert eine Antwort (Ordner, Saison, Hinweise) |
| `spielpartner_aufnahme.zaehler_setzen` | Saison / Aufnahmen in Saison / Gesamt auf feste Werte |
| `spielpartner_aufnahme.aufnahme_zaehlen` | Aufnahme manuell mitzählen |
| `spielpartner_aufnahme.aufnahme_posten` | Statusbeitrag sofort posten |
| `spielpartner_aufnahme.dateiformat_anwenden` | Dateinamen erneut in OBS schreiben |

`spielpartner` ist die Kennung (z. B. `frank_visselff`) oder der Anzeigename; bei den letzten drei Services
bedeutet leer „aktueller Spielpartner“.

## Discord einrichten

Bot im Developer Portal anlegen, auf den Server einladen, Token in den Einstellungen eintragen.
Der Bot braucht im Forum-Kanal: *Kanäle ansehen*, *Beiträge erstellen*, *Nachrichten in Beiträgen senden*,
*Dateien anhängen*, *Links einbetten*. Die Kanal-ID steht beim Spielpartner (Rechtsklick auf das Forum → ID kopieren).
Ohne Token bleibt Discord aus – alles andere funktioniert weiter.

## Tests

```bash
pip install -r requirements_test.txt
pytest
```

## Weitere Doku

- [Migration vom alten System](docs/migration.md)
- [Dashboard-Beispiel](docs/dashboard.md)

## Bekannte Eigenheiten

- Die Zähler zeigen die Nummer, die die **nächste** Aufnahme bekommt (so verhielt sich das alte System auch);
  nach Aufnahme-Ende werden sie erhöht.
- Das PC-Ordner-Werkzeug ist ein eigener Baustein von dir; sind seine Entities nicht erreichbar, überspringt die
  Integration die Ordner-Schritte und sagt es in der Benachrichtigung (Saisonwechsel wird dann **nicht** erkannt).
- Das Kürzel `sc` (Schnauzencam) ist klein geschrieben, wie angegeben.
