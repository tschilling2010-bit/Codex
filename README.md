# Handschrift-Seiten Generator (Web-App, Option A)

Diese Lösung nutzt **React + Node/Express + PDFKit** (Option A), weil sie schnell startbar ist, plattformunabhängig läuft und serverseitig stabile PDF-Erzeugung mit Mehrseiten-Layout erlaubt.

## Was die App kann

- Text per Copy/Paste oder Tippen eingeben
- Papier wählen: `liniert`, `kariert`, `blanko`
- A4, frei einstellbare Ränder
- Stiftfarbe blau/schwarz
- Schriftgröße und Zeilenabstand
- Handschrift-Stil-Presets + Seed
- Unsauberkeit (Jitter/Rotation/Spacing)
- Vorschau der ersten 1–2 Seiten
- Mehrseitiger PDF-Export
- Aufzählungen mit Hanging Indent (`•`, `-`, `1)`)
- Unicode/Sonderzeichen (inkl. √ α β ≤ ≥ ≠ → €)

## Realistische Grenze (ehrlich)

Echte allographische Buchstabenformen pro Zeichen (wie aus Spezial-Handschrift-Engines) sind ohne dedizierte OpenType-Alternates oder eigene Glyphen-Engine nur begrenzt umsetzbar.
Diese Version liefert die praktikable Annäherung durch:

1. Font-Mix (3 Stilquellen)
2. Seeded Random (reproduzierbar)
3. Mikro-Variationen (Rotation/Baseline/Spacing)

## Projektstruktur

```txt
.
├─ client/                 # React UI + Vorschau
│  ├─ src/App.jsx
│  ├─ src/main.jsx
│  └─ src/styles.css
├─ server/                 # API + Layout + PDF
│  └─ src/
│     ├─ index.js          # API-Endpunkte
│     ├─ layout.js         # Umbruch, Aufzählungen, Seed-Random
│     └─ pdf.js            # PDF-Rendering
└─ package.json            # Workspaces + dev script
```

## Setup (Windows/Mac/Linux)

1. **Node.js 20+** installieren
2. Im Projektordner:

```bash
npm install
```

3. Dev starten (Frontend + Backend):

```bash
npm run dev
```

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:3001`

## Produktion

```bash
npm run build
npm run start
```

## Wichtige technische Punkte

### Automatischer Seitenumbruch
- Layout berechnet nutzbare Fläche aus A4 minus Ränder.
- Bei voller Seite wird eine neue Seite erzeugt.
- Zeilenabstand und Absatzabstand bleiben konsistent.

### Aufzählungen sauber
- Erkennung von `•`, `-`, `1)` am Zeilenanfang.
- Marker in linker Spalte.
- Text in eigener Spalte mit Hanging Indent.
- Folgezeilen eines Listenpunkts bleiben eingerückt.

### Seeded Random / Reproduzierbarkeit
- Gleicher Text + gleiche Settings + gleicher Seed => gleiches PDF.
- Verwendet für Stilwahl, Baseline-Jitter, Rotation, Zeichenabstand.

### Fallback bei Glyphen
- PDF nutzt DejaVu als breite Unicode-Abdeckung.
- Falls ein Stilfont fehlt, Fallback auf `DejaVuSans`.

## API

- `GET /api/examples` → 3 Beispieltexte
- `POST /api/layout` → Vorschau-Layout (max 2 Seiten)
- `POST /api/export/pdf` → PDF-Datei

## Optionaler Ausbau

- PNG-Export pro Seite via `sharp`/`pdf-poppler`
- Eigene Handschriftfonts einbinden
- Überschriften-Modus (größer, stärker geneigt)
- Randnotizen-Toggle
