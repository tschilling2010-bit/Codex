import PDFDocument from 'pdfkit';
import path from 'path';
import { fileURLToPath } from 'url';
import { createLayout } from './layout.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const FONT_PATHS = {
  hw1: '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
  hw2: '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf',
  hw3: '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Oblique.ttf',
  fallback: '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
};

function drawPaper(doc, settings, page, margin) {
  if (settings.paperType === 'blanko') return;
  const left = margin.left;
  const right = page.width - margin.right;

  if (settings.paperType === 'liniert') {
    doc.strokeColor('#b7d1ff').lineWidth(0.5);
    for (let y = margin.top; y <= page.height - margin.bottom; y += settings.lineHeight) {
      doc.moveTo(left, y + settings.fontSize * 0.45).lineTo(right, y + settings.fontSize * 0.45).stroke();
    }
  }

  if (settings.paperType === 'kariert') {
    const grid = settings.lineHeight;
    doc.strokeColor('#cddfff').lineWidth(0.4);
    for (let y = margin.top; y <= page.height - margin.bottom; y += grid) {
      doc.moveTo(left, y).lineTo(right, y).stroke();
    }
    for (let x = left; x <= right; x += grid) {
      doc.moveTo(x, margin.top).lineTo(x, page.height - margin.bottom).stroke();
    }
  }
}

export function generatePdfBuffer(text, settings) {
  const { pages, page, margin } = createLayout(text, settings);
  const doc = new PDFDocument({ size: [page.width, page.height], margin: 0 });
  Object.entries(FONT_PATHS).forEach(([k, v]) => doc.registerFont(k, v));

  const chunks = [];
  doc.on('data', (c) => chunks.push(c));

  pages.forEach((pg, idx) => {
    if (idx > 0) doc.addPage({ size: [page.width, page.height], margin: 0 });
    drawPaper(doc, settings, page, margin);

    pg.lines.forEach((line) => {
      line.runs.forEach((run) => {
        const fontName = FONT_PATHS[run.style] ? run.style : 'fallback';
        doc.save();
        doc.font(fontName);
        doc.fontSize(settings.fontSize);
        doc.fillColor(settings.penColor === 'blau' ? '#1b3fa8' : '#1a1a1a');
        const y = line.y + run.baselineJitter;
        doc.rotate(run.rotate, { origin: [run.x, y] });
        doc.text(run.text, run.x, y, { lineBreak: false, characterSpacing: run.charSpacing });
        doc.restore();
      });
    });
  });

  doc.end();
  return new Promise((resolve) => {
    doc.on('end', () => resolve(Buffer.concat(chunks)));
  });
}
