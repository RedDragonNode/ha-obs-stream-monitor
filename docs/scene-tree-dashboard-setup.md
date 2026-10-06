# Szenen-Baum-Dashboard einrichten

Optionale Funktion von OBS Stream Monitor: eine eigene Dashboard-Karte, die OBS' Szenen,
die Quellen darin und deren Filter zum Durchklicken zeigt — mit Schaltern für
Quellen-Sichtbarkeit (das Augen-Symbol in OBS) und Filter an/aus.

Technisch zwei getrennte Teile: Schalter-Entitäten (kommen von der Integration selbst) und
eine Dashboard-Karte (eine JavaScript-Datei, die die Integration mitliefert). Beide müssen
einmalig aktiviert werden.

## 1. Schalter-Entitäten aktivieren

Integration **OBS Stream Monitor** → **Konfigurieren** → ganz unten
**"Szenen-Baum aktivieren (Quellen/Filter als Schalter)"** anhaken → Absenden. Die
Integration lädt sich automatisch neu, kein Neustart nötig.

Ab jetzt fragt die Integration bei jeder Abfrage zusätzlich alle Szenen, deren Quellen und
deren Filter ab. Bei sehr vielen Szenen/Quellen kann das die Abfrage minimal verlangsamen —
für ein normales Streaming-Setup (ein paar Szenen, einige Quellen) kein Thema.

## 2. Die Dashboard-Karte als Ressource eintragen

Das kann Home Assistant nicht automatisch für dich tun — eine Integration darf keine
Lovelace-Ressource selbst eintragen. Einmalig von Hand:

1. **Einstellungen → Dashboards** → oben rechts die drei Punkte → **Ressourcen**
2. **Ressource hinzufügen**
3. **URL:** `/obs_stream_monitor_card/obs-scene-tree-card.js?v=0.5.5`
4. **Ressourcentyp:** JavaScript-Modul
5. Speichern

Falls der Dialog "Ressourcen" nicht sichtbar ist: unten links im Profil den "erweiterten
Modus" (Experten-Modus) einschalten, dann erscheint der Menüpunkt.

**Wichtig bei künftigen Updates:** Home Assistant/der Browser cached diese JS-Datei hartnäckig
unter ihrer URL — ein reines Integrations-Update + Neustart reicht oft nicht, die neue
Version wird angezeigt. Nach jedem Update, das die Karte selbst betrifft, die Ressourcen-URL
in Schritt 3 auf die neue Versionsnummer hochziehen (z. B. `?v=0.5.6`) und danach im Browser
hart neu laden (Strg+Shift+R). Die jeweils aktuelle Versionsnummer steht in den
Release-Notes.

**Updates mit Backend-Änderungen** (steht in den Release-Notes, z. B. "enthält
Backend-Änderungen") brauchen zusätzlich einen **Neustart von Home Assistant** - ein reiner
Browser-Hard-Refresh reicht dann nicht, weil sich auch Python-Code geändert hat, nicht nur
die Karte.

**Falls der Zugriff über eine eigene Domain mit vorgeschaltetem Reverse-Proxy/CDN läuft**
(z. B. Cloudflare), kann *das* die JS-Datei zusätzlich unabhängig vom `?v=`-Parameter am
Rand cachen — dann helfen weder Versionsnummer noch Hard-Refresh im Browser. Erkennbar daran,
dass ein direkter Aufruf im lokalen Netz (z. B. `http://<HA-Hostname>.local:8123/...`) die
neue Version zeigt, über die öffentliche Domain aber weiterhin die alte. In dem Fall den
Cache des Proxys/CDN gezielt leeren (bei Cloudflare z. B. Caching → Configuration →
"Purge Everything", oder gezielt die URL `/obs_stream_monitor_card/*` purgen).

## 3. Karte zu einem Dashboard hinzufügen

1. Ein Dashboard öffnen (oder ein neues anlegen) → oben rechts die drei Punkte →
   **Dashboard bearbeiten**
2. **Karte hinzufügen** → nach "OBS Szenen-Baum" suchen (erscheint in der Liste, weil die
   Karte sich selbst dort einträgt) → auswählen
3. Keine Pflichtfelder nötig — einfach speichern

Falls mehrere OBS-Installationen/Integrationseinträge existieren und die Karte nur eine
davon zeigen soll, im Karten-Code (YAML-Editor der Karte) ein `entry_id` ergänzen:

```yaml
type: custom:obs-scene-tree-card
entry_id: DEIN_CONFIG_ENTRY_ID
```

Die `entry_id` steht in der URL, wenn man in **Einstellungen → Geräte & Dienste** auf den
jeweiligen OBS-Stream-Monitor-Eintrag klickt (der Teil nach `.../integrations/integration/
obs_stream_monitor` bzw. die ID in der Geräte-URL).

### Variante: eine eigene Karte pro Szene

Statt einer Karte mit Szenen-Auswahl kann jede Szene auch ihre eigene, fest zugeordnete
Karte bekommen — dann liegen z. B. alle Szenen nebeneinander im Raster, ohne erst in die
Szenen-Ebene klicken zu müssen. Dafür bei der Karten-Konfiguration das Feld `scene` mit dem
exakten Szenennamen setzen (Groß-/Kleinschreibung muss stimmen):

```yaml
type: custom:obs-scene-tree-card
scene: Spiele Saison
```

```yaml
type: custom:obs-scene-tree-card
scene: Pause
```

Jede so eingerichtete Karte zeigt direkt die Quellen dieser einen Szene (samt
Sichtbarkeits-Schaltern); ein Klick auf eine Quelle führt wie gewohnt eine Ebene tiefer zu
deren Filtern. Nur die Szenen-Ebene selbst (zu anderen Szenen wechseln) gibt es in diesem
Modus nicht — dafür legt man eben für jede Szene eine eigene Karte an. Mehrere dieser
Karten lassen sich z. B. über eine "Raster"-Stapelkarte (`type: grid`) nebeneinander
anordnen.

## Bedienung

- **Erste Ebene:** alle Szenen. Ein roter Punkt markiert die aktuell aktive Szene.
- Auf eine Szene klicken → **zweite Ebene:** die Quellen dieser Szene, mit Schalter für
  Sichtbarkeit (Augen-Symbol in OBS) ganz rechts.
- Auf eine Quelle klicken (nicht auf den Schalter) → **dritte Ebene:** die Filter dieser
  Quelle, mit Schalter für aktiv/inaktiv.
- Über die Brotkrumen-Navigation oben (Szenen › Szenenname › Quellenname) geht's wieder
  zurück.
- Unter jeder Quelle und jedem Filter steht klein "Entitäts-ID" mit Kopier-Symbol. Mit der
  Maus draufhalten zeigt die volle `switch...`-ID als Tooltip, draufklicken kopiert sie
  vollständig in die Zwischenablage - praktisch, um sie in Automatisierungen, Skripten oder
  anderen Dashboards zu verwenden, ohne sie vorher unter Einstellungen → Entitäten suchen zu
  müssen. Der Klick darauf navigiert nicht in die nächste Ebene, er kopiert nur.
- Neben jeder Quelle und jedem Filter steht außerdem ein **Zahnrad-Symbol**. Ein Klick
  öffnet einen Dialog zum Bearbeiten der echten OBS-Einstellungen dieser Quelle/dieses
  Filters (siehe "Einstellungen bearbeiten" unten).

## Einstellungen bearbeiten

Über das Zahnrad-Symbol neben einer Quelle bzw. einem Filter öffnet sich ein Dialog mit
einem **generischen Formular**: Es zeigt alle Felder, die OBS für diese Quelle/diesen Filter
zurückgibt, jeweils passend als Text-, Zahlen- oder Häkchen-Feld; verschachtelte Werte
(Objekte, Listen) erscheinen als JSON-Text zum Bearbeiten. "Speichern" schreibt die
geänderten Werte direkt zurück nach OBS (`SetInputSettings`/`SetSourceFilterSettings`).

Wichtig dabei:

- Die Feldnamen sind die **rohen, technischen** Namen, wie obs-websocket sie liefert - keine
  deutschen oder beschönigten Bezeichnungen, wie man sie aus dem OBS-Fenster selbst kennt.
- Ungültiges JSON in einem JSON-Feld wird vor dem Speichern erkannt und mit einer Fehlermeldung
  abgelehnt, ohne die bisherigen Eingaben zu verwerfen. Alles andere wird unverändert an OBS
  weitergegeben - OBS kann einen Wert selbst ablehnen oder sich damit unerwartet verhalten.
- Das ist eine fortgeschrittene Funktion für alle, die wissen, welches Feld sie ändern wollen
  (z. B. um eine Textquelle, eine Mediendatei oder Chroma-Key-Werte fernzusteuern, etwa für
  IRL-Streams/Aufnahmen). Im Zweifel vorher in OBS selbst nachsehen, welchen Effekt ein Feld
  hat.

## Bekannte Einschränkungen

- **Gruppen** (verschachtelte Szenen innerhalb einer Szene) werden in der ersten Version
  nicht aufgelöst — nur normale Quellen.
- Wird eine Quelle/Szene/Filter in OBS **umbenannt**, erscheint sie als neuer Eintrag; der
  alte Schalter wird "nicht verfügbar" und kann in Home Assistant von Hand gelöscht werden
  (Einstellungen → Geräte & Dienste → OBS Stream Monitor → Entitäten → den alten Eintrag
  löschen).
- Die Karte zeigt nur, was die Integration zuletzt abgefragt hat (wie alle Sensoren hier,
  alle ~10 Sekunden aktuell) — keine Echtzeit-Push-Updates von OBS.

## Fehlersuche

| Symptom | Ursache | Lösung |
|---|---|---|
| Karte "OBS Szenen-Baum" taucht beim Kartenhinzufügen nicht auf | Ressource (Schritt 2) fehlt oder falsch eingetragen, oder Browser-Cache | URL exakt prüfen, Seite neu laden (Strg+Shift+R) |
| Nach einem Update verhält sich die Karte noch wie vorher (z. B. `scene`-Feld ohne Wirkung) | Alte JS-Datei noch im Cache - weder Integrations-Update+Neustart noch normales Neuladen der Seite erzwingen das Nachladen | Ressourcen-URL um `?v=<neue Version>` ergänzen (siehe oben) und hart neu laden (Strg+Shift+R); zusätzlich prüfen, ob die Integration wirklich auf der neuen Version ist (Geräte & Dienste → OBS Stream Monitor) |
| Karte zeigt "Noch keine Daten" dauerhaft | Schritt 1 (Szenen-Baum aktivieren) nicht gemacht, oder OBS gerade nicht erreichbar | Integrations-Optionen prüfen; Sensor "Aktuelle Szene" sollte einen Wert zeigen |
| Schalter lässt sich nicht bedienen (ausgegraut) | Entität aktuell "nicht verfügbar", meist weil OBS nicht läuft oder die Quelle/der Filter inzwischen umbenannt/gelöscht wurde | OBS-Erreichbarkeit prüfen; bei Umbenennung siehe "Bekannte Einschränkungen" oben |
| Neue Version zeigt sich im lokalen Netz (`<HA-Hostname>.local:8123`) korrekt, über die öffentliche Domain aber weiterhin alt | Reverse-Proxy/CDN vor der Domain (z. B. Cloudflare) cached die JS-Datei unabhängig vom `?v=`-Parameter | Cache des Proxys/CDN gezielt leeren (siehe "Wichtig bei künftigen Updates" oben) |
