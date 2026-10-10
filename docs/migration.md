# Migration vom alten System

Wichtig vorab: **Altes und neues System dürfen nicht gleichzeitig in OBS schreiben.** Die alte Automation
„Aufnahme beendet – Zähler hochzählen“ schreibt nach jeder Aufnahme das alte Dateiformat (mit den alten
Zählern) in alle OBS-Filter und überschreibt damit das Format der Integration. Genauso postet die alte
5-Minuten-Automation weiter in Discord. Beide also ausschalten, sobald die Integration übernimmt.

## 1. Spielpartner anlegen

Pro Spielpartner: *Spielpartner hinzufügen*. Kennung (z. B. `frank_visselff`), Anzeigename, Ordner-Nummer und
Discord-Forum-Kanal-ID eintragen. Die Startwerte für Saison, Aufnahmen in Saison und Aufnahmen gesamt aus den
alten Zählern (`counter.saison_mit_<kennung>`, `counter.aufnahmen_in_aktueller_saison_mit_<kennung>`,
`counter.gesamt_aufnahmen_mit_<kennung>`) von Hand übernehmen. Später lassen sie sich an den Zahlenfeldern des
Spielpartner-Geräts korrigieren.

## 2. Cams für Discord auswählen

Bei jeder Cam, die im Discord-Beitrag erscheinen soll, **„In Discord posten“** anhaken (und eine Kamera für den
Schnappschuss hinterlegen).

## 3. Testlauf

Button *Aufnahme vorbereiten* drücken, Benachrichtigung lesen, in OBS Pfad und Dateinamen prüfen.

## 4. Altes System abschalten

- Automationen *Aufnahme beendet – Zähler hochzählen* und *Aufnahme läuft 5 Min – …* ausschalten
- Skript `script.aufnahme_vorbereitung` und `script.obs_source_record_format` nicht mehr aufrufen und später entfernen
- Helfer pro Spielpartner (Zähler, Thread, Kanal-ID, Dateiformat, Speicher-Adresse, Ordner) später löschen
- Dashboard-Knöpfe auf den neuen Button/Service umstellen (siehe [Dashboard](dashboard.md))

Nicht zur Integration gehören und bleiben bestehen: Lichtsteuerung (*Saison ist zuende*,
*Saison aufnahmen => Licht Steuerung*) und alles von ha-obs-stream-monitor.
