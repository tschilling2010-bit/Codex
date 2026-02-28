import express from 'express';
import cors from 'cors';
import { createLayout } from './layout.js';
import { generatePdfBuffer } from './pdf.js';

const app = express();
app.use(cors());
app.use(express.json({ limit: '1mb' }));

const defaultSettings = {
  paperType: 'liniert',
  pageFormat: 'A4',
  marginLeftMm: 20,
  marginRightMm: 15,
  marginTopMm: 20,
  marginBottomMm: 20,
  penColor: 'blau',
  fontSize: 18,
  lineHeight: 26,
  stylePreset: 'classic',
  seed: '42',
  messiness: 35,
  pressureVariation: true
};

app.get('/api/examples', (_req, res) => {
  res.json({
    examples: [
      'Heute üben wir Brüche: 1/2 + 1/4 = 3/4.\n• Merke: Nenner gleich machen.\n• Sonderzeichen: √, α, β, ≤, ≥, ≠, →.',
      'Einkaufsliste:\n- Milch 1,5L\n- Brot\n- Äpfel (3x)\nGesamt: 12,40 €',
      '1) Physik-Notiz\nSpannung U = 12V, Strom I = 0,5A.\nLeistung P = U·I = 6W ⚡\n"Sauber messen!"'
    ]
  });
});

app.post('/api/layout', (req, res) => {
  const text = req.body.text || '';
  const settings = { ...defaultSettings, ...(req.body.settings || {}) };
  const out = createLayout(text, settings, 2);
  res.json(out);
});

app.post('/api/export/pdf', async (req, res) => {
  const text = req.body.text || '';
  const settings = { ...defaultSettings, ...(req.body.settings || {}) };
  const pdf = await generatePdfBuffer(text, settings);
  res.setHeader('Content-Type', 'application/pdf');
  res.setHeader('Content-Disposition', 'attachment; filename="handschrift.pdf"');
  res.send(pdf);
});

const port = process.env.PORT || 3001;
app.listen(port, () => console.log(`API on :${port}`));
