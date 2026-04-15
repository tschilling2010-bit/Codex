# HefterPro

**Schöne Schulblätter — in wenigen Sekunden.**

HefterPro ist eine Web-App für Schüler:innen mit genau zwei Funktionen:

1. **Text zu Handschrift** — realistische Druckschrift aus deinem Tipptext,
   komplett offline und ohne KI.
2. **Automatische Hefterblatt-Erstellung** — Bilder, PDFs und Texte werden
   analysiert und zu einem strukturierten, lernfreundlichen Hefterblatt
   zusammengefügt.

Es gibt **keine Authentifizierung**, keine Logins, keine Konten.

---

## Schnellstart

```bash
./run.sh
```

Danach ist die App unter <http://localhost:8000> erreichbar.

Benötigt wird Python ≥ 3.10. Das Skript legt ein virtuelles Env an,
installiert Abhängigkeiten und startet `uvicorn` im Reload-Modus.

### Manuell

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Projektstruktur

```
backend/
  main.py                FastAPI-Entry
  config.py              Pfade, Seitenformat, Defaults
  models/schemas.py      Pydantic-Schemas
  routers/               API-Endpunkte (handwriting, hefter, projects, settings)
  services/
    charset.py           Zeichensatz fürs Template
    glyph_engine.py      Speicher- und Zugriffsschicht für Glyphen
    template_service.py  Template-Generierung und Upload-Auswertung
    rendering.py         Text-→-Handschrift-Renderer
    file_processing.py   PDF-/Bild-/Text-Extraktion
    hefter_generator.py  Strukturierung & Layout des Hefterblatts
    export.py            PDF/PNG/JPG-Export
    projects.py          Projekt-Speicherung und -Verwaltung
    settings_store.py    App-Einstellungen
  storage/               Persistenz (Profile, Projekte, Exporte, Uploads)

frontend/
  index.html             Landingpage
  dashboard.html         Dashboard mit 2 Hauptkarten
  handwriting.html       Funktion 1
  hefter.html            Funktion 2
  preview.html           Blatt-Vorschau
  downloads.html         Fertige Exporte
  settings.html          Voreinstellungen
  css/styles.css         Design-System
  js/                    Page-spezifische Scripts + API-Wrapper
```

---

## API-Überblick

| Methode | Pfad                                      | Beschreibung                                  |
|--------:|-------------------------------------------|-----------------------------------------------|
| GET     | `/api/health`                             | Health-Check                                  |
| GET     | `/api/handwriting/profile/list`           | Profile auflisten                             |
| DELETE  | `/api/handwriting/profile/{id}`           | Profil löschen                                |
| POST    | `/api/handwriting/template/create`        | Neues Template + Profil-Stub erzeugen         |
| POST    | `/api/handwriting/template/upload`        | Ausgefülltes Template als Bilder hochladen    |
| POST    | `/api/handwriting/render`                 | Text in Handschrift rendern                   |
| POST    | `/api/handwriting/export/pdf`             | Handschrift-Projekt als PDF exportieren       |
| POST    | `/api/handwriting/export/image`           | Handschrift-Projekt als PNG/JPG exportieren   |
| POST    | `/api/hefter/upload`                      | Dateien für ein Hefter-Projekt hochladen      |
| POST    | `/api/hefter/process`                     | Hefterblatt erzeugen                          |
| GET     | `/api/hefter/preview/{id}`                | Struktur-Dokument abrufen                     |
| POST    | `/api/hefter/export/pdf`                  | Hefter als PDF exportieren                    |
| POST    | `/api/hefter/export/image`                | Hefter als PNG/JPG exportieren                |
| GET     | `/api/projects/`                          | Alle Projekte                                 |
| GET     | `/api/projects/{id}`                      | Einzelnes Projekt                             |
| DELETE  | `/api/projects/{id}`                      | Projekt löschen                               |
| GET     | `/api/projects/{id}/pages/{n}`            | Seitenvorschau (PNG)                          |
| GET     | `/api/settings/`                          | Einstellungen lesen                           |
| PUT     | `/api/settings/`                          | Einstellungen speichern                       |

Generierte Dateien werden unter `/files/exports/...` und `/files/templates/...`
statisch ausgeliefert.

---

## Funktionsweise

### Text → Handschrift (offline, ohne KI)

Jedes Profil ist eine Sammlung transparenter PNG-Glyphen. Das
**Standard-Profil** wird beim ersten Start programmatisch erzeugt: ein
sauber schreibender Sans-Serif-Font wird pro Variante leicht rotiert und
skaliert — kein Cursive, sondern klare Druckschrift.

Für ein **eigenes Profil** wird ein A4-Template erzeugt: jede Zelle trägt
ein Hinweiszeichen und einen festen, geometrisch bekannten Schreibbereich.
Der Nutzer füllt das Blatt aus, fotografiert/scannt es und lädt die Bilder
hoch. Der Server schneidet jede Zelle über die gespeicherten Koordinaten
zu, ermittelt den Tintenbereich und speichert das Glyph als transparentes
PNG — mehrere Varianten pro Zeichen für natürliche Abwechslung.

Beim Rendern werden Glyphen pro Buchstabe zufällig aus den verfügbaren
Varianten gewählt, leicht in Größe, Position und Rotation variiert und mit
natürlichem Zeilen-/Wortabstand auf das Blatt gesetzt. Absätze, Zeilen­
umbrüche und Stichpunkte (`- …`, `• …`) werden erkannt.

### Hefterblatt (Heuristik, optional KI)

`file_processing` liest PDFs und Textdateien aus und sammelt Bildpfade.
`hefter_generator` leitet Titel, Unterüberschriften, Abschnitte, Bullets
und Merkkasten-Kandidaten aus dem Text ab. Das Ergebnis wird als
Pydantic-Dokument gespeichert und anschließend auf A4-Blätter gerendert
(Titel, Akzentbalken, Bullet-Listen, Merkkästen).

Wird `HEFTERPRO_AI=1` gesetzt, wird optional eine Datei
`backend/services/ai_structuring.py` aufgerufen, um die Struktur zu
verbessern — fehlt sie oder schlägt sie fehl, greift die Heuristik.

---

## Umgebungsvariablen

| Variable             | Default                    | Zweck                                   |
|----------------------|----------------------------|-----------------------------------------|
| `HEFTERPRO_STORAGE`  | `backend/storage`          | Speicherort für Profile/Projekte/…      |
| `HEFTERPRO_AI`       | `0`                        | Optionalen KI-Hook aktivieren           |
