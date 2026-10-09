# Szenen-Baum-Dashboard einrichten

Optionale Funktion von OBS Stream Monitor: eine eigene Dashboard-Karte, die OBS' Szenen,
die Quellen darin und deren Filter zum Durchklicken zeigt — mit Schaltern für
Quellen-Sichtbarkeit (das Augen-Symbol in OBS) und Filter an/aus. Dieselbe Ressource bringt
außerdem eine zweite, kleinere Karte mit ("OBS Einstellung" - siehe "Einzelne Einstellung
als eigene Karte" weiter unten), mit der sich ein einzelnes Feld fest auf dem Dashboard
anheften lässt.

Technisch zwei getrennte Teile: Schalter-Entitäten (kommen von der Integration selbst) und
die Dashboard-Karten (eine JavaScript-Datei, die die Integration mitliefert). Beide müssen
einmalig aktiviert werden.

## 1. Schalter-Entitäten aktivieren

Integration **OBS Stream Monitor** → **Konfigurieren** → ganz unten
**"Szenen-Baum aktivieren (Quellen/Filter als Schalter)"** anhaken → Absenden. Die
Integration lädt sich automatisch neu, kein Neustart nötig.

Ab jetzt fragt die Integration bei jeder Abfrage zusätzlich alle Szenen, deren Quellen und
deren Filter ab. Bei sehr vielen Szenen/Quellen kann das die Abfrage minimal verlangsamen —
für ein normales Streaming-Setup (ein paar Szenen, einige Quellen) kein Thema.

## 2. Die Dashboard-Karten als Ressource eintragen

Das kann Home Assistant nicht automatisch für dich tun — eine Integration darf keine
Lovelace-Ressource selbst eintragen. Einmalig von Hand (gilt für beide Karten, "OBS
Szenen-Baum" und "OBS Einstellung" - beide stecken in derselben Datei):

1. **Einstellungen → Dashboards** → oben rechts die drei Punkte → **Ressourcen**
2. **Ressource hinzufügen**
3. **URL:** `/obs_stream_monitor_card/obs-scene-tree-card.js?v=0.7.4`
4. **Ressourcentyp:** JavaScript-Modul
5. Speichern

Falls der Dialog "Ressourcen" nicht sichtbar ist: unten links im Profil den "erweiterten
Modus" (Experten-Modus) einschalten, dann erscheint der Menüpunkt.

**Wichtig bei künftigen Updates:** Home Assistant/der Browser cached diese JS-Datei hartnäckig
unter ihrer URL — ein reines Integrations-Update + Neustart reicht oft nicht, die neue
Version wird angezeigt. Nach jedem Update, das eine der beiden Karten betrifft, die
Ressourcen-URL in Schritt 3 auf die neue Versionsnummer hochziehen (z. B. `?v=0.7.4`) und
danach im Browser hart neu laden (Strg+Shift+R). Die jeweils aktuelle Versionsnummer steht in
den Release-Notes.

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

Für eine wachsende Liste an eingebauten OBS-Quellen/-Filtern und gängigen Community-Plugins
(siehe Release-Notes v0.5.6) zeigt das Formular statt des rohen Feldnamens eine "schöne"
Beschriftung - automatisch auf Deutsch oder Englisch, je nachdem, was in Home Assistant unter
**Einstellungen → Allgemein → Sprache** eingestellt ist. Der rohe Name steht weiterhin klein
daneben. Ist eine Quelle/ein Filter (noch) nicht in dieser Tabelle, zeigt das Formular wie
gehabt nur den rohen Namen - nichts bricht dadurch, es ist rein kosmetisch.

Wichtig dabei:

- Bei unbekannten Quellen/Filtern (oder Feldern ohne Übersetzung) sind die Feldnamen die
  **rohen, technischen** Namen, wie obs-websocket sie liefert.
- Ungültiges JSON in einem JSON-Feld wird vor dem Speichern erkannt und mit einer Fehlermeldung
  abgelehnt, ohne die bisherigen Eingaben zu verwerfen. Alles andere wird unverändert an OBS
  weitergegeben - OBS kann einen Wert selbst ablehnen oder sich damit unerwartet verhalten.
- Das ist eine fortgeschrittene Funktion für alle, die wissen, welches Feld sie ändern wollen
  (z. B. um eine Textquelle, eine Mediendatei oder Chroma-Key-Werte fernzusteuern, etwa für
  IRL-Streams/Aufnahmen). Im Zweifel vorher in OBS selbst nachsehen, welchen Effekt ein Feld
  hat.
- Solange der Dialog offen ist, pausiert die Karte ihre automatischen Aktualisierungen (seit
  v0.5.7) - vorher gingen noch nicht gespeicherte Eingaben durch die ständigen Live-Updates
  verloren. Nach "Speichern" oder "Abbrechen" aktualisiert sich die Karte sofort wieder normal.
- Manche eingebauten OBS-Quellen melden ihren "Typ" intern versioniert (z. B.
  `text_gdiplus_v3` statt `text_gdiplus`, `color_source_v2` statt `color_source`) - seit
  v0.5.9 erkennt die Übersetzungstabelle das automatisch und zeigt trotzdem die schönen
  Beschriftungen an.

## Einzelne Einstellung als eigene Karte

Seit v0.7.0 gibt es zusätzlich zum Zahnrad-Dialog eine eigene, kleinere Karte
**"OBS Einstellung"** (`custom:obs-setting-card`), die genau **ein** Feld fest auf dem
Dashboard zeigt - praktisch für Werte, die man oft braucht (z. B. den Aufnahmepfad), ohne
jedes Mal den Dialog zu öffnen. Dieselbe Ressource wie oben reicht dafür aus, kein
zusätzlicher Eintrag unter "Ressourcen" nötig - und anders als die große Karte braucht sie
auch nicht "Szenen-Baum aktivieren" (Schritt 1 oben): sie spricht OBS direkt über Quellen-/
Filternamen an, ganz unabhängig von den Szenen-Baum-Schalter-Entitäten.

Karte hinzufügen wie gewohnt: **Zum Dashboard hinzufügen** → Reiter **"Nach Karte"** (nicht
"Nach Entität" - dort erscheint sie nicht, da sie sich nicht an eine einzelne Entität bindet,
siehe oben) → nach "OBS Einstellung" suchen. Seit v0.7.2 öffnet sich dabei ein richtiges
Formular statt direkt des rohen YAML-/Code-Editors - mindestens `source` und `field`
ausfüllen:

```yaml
type: custom:obs-setting-card
source: Kesselcam
field: path
```

Die Felder "Quelle" und "Filter" im Formular bieten dabei Autovervollständigung mit den
exakten Namen aus den bereits bestehenden "Szenen-Baum"-Schalter-Entitäten (sofern "Szenen-
Baum aktivieren", Schritt 1 oben, an ist) - praktisch, um sich nicht bei langen Filternamen
zu vertippen. Ohne aktivierten Szenen-Baum bleiben die Felder normale Texteingaben.

Seit v0.7.3 bekommt auch **"Feld (field)"** Namensvorschläge: sobald "Quelle" (und bei einem
Filter-Feld zusätzlich "Filter") ausgefüllt ist und der Typ der Quelle/des Filters erkannt
wird, schlägt das Formular die bekannten rohen Feldnamen dieses Typs vor, mit derselben
schönen Bezeichnung wie im Zahnrad-Dialog (z. B. "Image File (file)"). Bei einem nicht
erkannten Typ bleibt das Feld wie gehabt ein einfaches Textfeld.

Ebenfalls seit v0.7.3 behoben: Das Formular hat zuvor alle ~10 Sekunden die gerade
eingegebene, noch nicht bestätigte Eingabe verworfen (derselbe Bug wie zuvor im
Zahnrad-Dialog, siehe "Einstellungen bearbeiten" oben) - jetzt baut sich das Formular nur
noch beim ersten Öffnen bzw. bei einer echten Konfigurationsänderung neu auf.

Seit v0.7.4 behoben: Ein übernommener Namensvorschlag für "Quelle" oder "Filter" wurde
automatisch getrimmt (Leerzeichen am Anfang/Ende entfernt). Hat eine Quelle in OBS selbst
ein Leerzeichen am Ende ihres Namens (kommt gelegentlich beim Benennen vor), wurde dadurch
genau dieses Leerzeichen abgeschnitten - mit der Folge, dass für diese Quelle keine
Filter-Vorschläge mehr erschienen (der gespeicherte Name stimmte nicht mehr exakt mit dem
echten OBS-Namen überein) und die Karte selbst beim Speichern mit "No source/filter was
found" fehlgeschlagen wäre. Werte werden jetzt unverändert übernommen, exakt wie OBS sie
meldet - nur ein komplett leeres Feld gilt weiterhin als "leer".

Für die Einstellung eines **Filters** zusätzlich `filter` angeben:

```yaml
type: custom:obs-setting-card
source: Kesselcam => Hauptstream
filter: Source Record => Kesselcam (4K)
field: path
```

- `source`: der Name der Quelle **wie in OBS selbst** (nicht der Home-Assistant-Entitätsname)
- `field`: der rohe, technische Feldname - am einfachsten einmal über den Zahnrad-Dialog
  derselben Quelle/desselben Filters nachsehen (steht dort klein neben jeder Beschriftung in
  Klammern, siehe "Einstellungen bearbeiten" oben)
- `filter` (optional): Name eines Filters auf dieser Quelle, falls das Feld zu einem Filter
  statt zur Quelle selbst gehört - **muss exakt stimmen**, inklusive eines eventuellen
  Zusatzes im Namen (z. B. heißt ein Filter nicht zwangsläufig nur "Source Record", sondern
  z. B. vollständig "Source Record => Kesselcam (4K)"). Seit v0.7.1 zeigt der Zahnrad-Dialog
  den vollen Namen als Tooltip beim Daraufhalten mit der Maus, falls er in der Titelzeile
  abgeschnitten dargestellt wird.
- `title` (optional): eigene Kartenüberschrift statt der automatisch ermittelten Beschriftung
- `entry_id` (optional): nur nötig bei mehreren OBS-Installationen/Integrationseinträgen -
  wird bei nur einem Eintrag automatisch erkannt

Die Karte lädt den aktuellen Wert direkt beim Öffnen des Dashboards (und über das
Aktualisieren-Symbol oben rechts jederzeit erneut) - anders als die Sensoren hier läuft das
nicht über die normale 10-Sekunden-Abfrage. Häkchen-Felder (boolean) werden sofort beim
Umschalten gespeichert, alle anderen Feldtypen (Text, Zahl, JSON) erst nach Klick auf
"Speichern".

Mehrere dieser Karten lassen sich z. B. über eine "Raster"-Stapelkarte (`type: grid`)
nebeneinander anordnen - etwa eine kleine Zusammenstellung der am häufigsten geänderten
Werte, ohne jedes Mal durch den Szenen-Baum navigieren zu müssen.

## Einstellungen per Automatisierung setzen

Seit v0.5.8 gibt es dieselbe Funktion wie den Zahnrad-Dialog auch als ganz normalen Home
Assistant-Service, nutzbar aus Automatisierungen und Skripten - z. B. um bei Stream-/
Aufnahmestart automatisch einen Text, eine Mediendatei oder Chroma-Key-Werte zu setzen, ohne
den Dialog von Hand zu öffnen (praktisch kombiniert mit dem bereits bestehenden "OBS
starten"-Button für volle Fernsteuerung bei IRL-Streams/Aufnahmen).

**Service:** `obs_stream_monitor.set_settings`

**Ziel (Target):** eine der vorhandenen Schalter-Entitäten der "Szenen-Baum"-Funktion -
`switch.obs_sceneitem_*` für eine Quelle, `switch.obs_filter_*` für einen Filter. Genau die
Entitäts-ID, die man über das Kopier-Symbol an jeder Quelle/jedem Filter bekommt (siehe
"Bedienung" oben) - welcher OBS-Eintrag, welche Quelle und ggf. welcher Filter gemeint sind,
ermittelt der Service automatisch aus dieser Entität, nichts muss man selbst eintippen.

**Datenfeld `settings`:** ein Objekt mit den zu ändernden Feldern, in denselben rohen,
technischen Feldnamen wie im Zahnrad-Dialog (klein neben der jeweiligen Beschriftung zu
sehen). Es werden nur die angegebenen Felder geändert (Overlay/Merge) - alle anderen
Einstellungen der Quelle/des Filters bleiben unangetastet, man muss also nicht das komplette
Einstellungs-Objekt mitschicken.

Beispiel-Automatisierung (setzt bei Stream-Start einen Text und eine Chroma-Key-Farbe):

```yaml
automation:
  - alias: "OBS: Text bei Stream-Start setzen"
    trigger:
      - platform: state
        entity_id: binary_sensor.obs_livestream
        to: "on"
    action:
      - service: obs_stream_monitor.set_settings
        target:
          entity_id: switch.obs_sceneitem_spiele_saison_textoverlay
        data:
          settings:
            text: "Jetzt live!"
```

Auch über **Entwicklerwerkzeuge → Aktionen** direkt testbar (Ziel-Entität auswählen,
`settings` als Objekt eingeben).

## Bekannte Einschränkungen

- **Gruppen** (verschachtelte Szenen innerhalb einer Szene) werden in der ersten Version
  nicht aufgelöst — nur normale Quellen.
- Wird eine Quelle/Szene/Filter in OBS **entfernt oder umbenannt**, verschwindet der
  zugehörige Schalter seit v0.7.6 automatisch wieder aus Home Assistant (statt nur dauerhaft
  "nicht verfügbar" zu bleiben) - spätestens beim nächsten Poll (max. 10s). Eine Umbenennung
  sieht dabei technisch wie "alt entfernt, neu hinzugekommen" aus (obs-websocket liefert
  keine stabile ID, die eine Umbenennung von einer Entfernung unterscheidbar macht), daher
  bekommt eine umbenannte Quelle/ein umbenannter Filter einen frischen Schalter statt dass
  der alte weiterverwendet wird - in Dashboards/Automatisierungen also ggf. neu referenzieren.
  (Vor v0.7.6 blieb der alte Schalter stattdessen stehen und musste von Hand gelöscht werden,
  Einstellungen → Geräte & Dienste → OBS Stream Monitor → Entitäten.)
- Die Karte zeigt nur, was die Integration zuletzt abgefragt hat (wie alle Sensoren hier,
  alle ~10 Sekunden aktuell) — keine Echtzeit-Push-Updates von OBS.

## Fehlersuche

| Symptom | Ursache | Lösung |
|---|---|---|
| Karte "OBS Szenen-Baum" oder "OBS Einstellung" taucht beim Kartenhinzufügen nicht auf | Ressource (Schritt 2) fehlt oder falsch eingetragen, oder Browser-Cache | URL exakt prüfen, Seite neu laden (Strg+Shift+R) |
| "OBS Einstellung"-Karte zeigt `Feld "..." nicht in den Einstellungen gefunden` | Feldname (`field`) stimmt nicht exakt mit dem rohen Namen überein, oder `source`/`filter` falsch geschrieben | Einmal den Zahnrad-Dialog derselben Quelle/desselben Filters öffnen und den exakten rohen Feldnamen (in Klammern) übernehmen |
| "OBS Einstellung"-Karte zeigt `No filter was found ...` / `No source was found ...` (code 600) | `source`/`filter` stimmt nicht exakt mit dem Namen in OBS überein - Filternamen haben oft einen Zusatz (z. B. "Source Record => Kesselcam (4K)" statt nur "Source Record") | Exakten Namen im Zahnrad-Dialog derselben Quelle nachsehen (Tooltip bei abgeschnittenem Titel, seit v0.7.1) oder direkt in OBS |
| "OBS Einstellung"-Karte zeigt `Mehrere OBS-Stream-Monitor-Einträge gefunden` | Mehr als eine OBS-Installation/Integrationseintrag vorhanden, Karte kann nicht automatisch raten, welcher gemeint ist | `entry_id` in der Karten-Konfiguration ergänzen (siehe Schritt 3 oben, "Falls mehrere OBS-Installationen...") |
| Nach einem Update verhält sich die Karte noch wie vorher (z. B. `scene`-Feld ohne Wirkung) | Alte JS-Datei noch im Cache - weder Integrations-Update+Neustart noch normales Neuladen der Seite erzwingen das Nachladen | Ressourcen-URL um `?v=<neue Version>` ergänzen (siehe oben) und hart neu laden (Strg+Shift+R); zusätzlich prüfen, ob die Integration wirklich auf der neuen Version ist (Geräte & Dienste → OBS Stream Monitor) |
| Karte zeigt "Noch keine Daten" dauerhaft | Schritt 1 (Szenen-Baum aktivieren) nicht gemacht, oder OBS gerade nicht erreichbar | Integrations-Optionen prüfen; Sensor "Aktuelle Szene" sollte einen Wert zeigen |
| Schalter lässt sich nicht bedienen (ausgegraut) | Entität aktuell "nicht verfügbar", meist weil OBS nicht läuft; läuft OBS und bleibt es trotzdem ausgegraut, verschwindet der Schalter ab v0.7.6 beim nächsten Poll von selbst (Quelle/Filter wurde entfernt/umbenannt) | OBS-Erreichbarkeit prüfen; sonst kurz abwarten (max. 10s) |
| Neue Version zeigt sich im lokalen Netz (`<HA-Hostname>.local:8123`) korrekt, über die öffentliche Domain aber weiterhin alt | Reverse-Proxy/CDN vor der Domain (z. B. Cloudflare) cached die JS-Datei unabhängig vom `?v=`-Parameter | Cache des Proxys/CDN gezielt leeren (siehe "Wichtig bei künftigen Updates" oben) |
