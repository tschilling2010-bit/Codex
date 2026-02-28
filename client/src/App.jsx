import { useEffect, useMemo, useState } from 'react';

const API = 'http://localhost:3001';

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

export default function App() {
  const [text, setText] = useState('');
  const [settings, setSettings] = useState(defaultSettings);
  const [layout, setLayout] = useState(null);
  const [examples, setExamples] = useState([]);

  useEffect(() => {
    fetch(`${API}/api/examples`).then((r) => r.json()).then((d) => {
      setExamples(d.examples);
      setText(d.examples[0]);
    });
  }, []);

  useEffect(() => {
    const id = setTimeout(async () => {
      const r = await fetch(`${API}/api/layout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, settings })
      });
      setLayout(await r.json());
    }, 180);
    return () => clearTimeout(id);
  }, [text, settings]);

  const pageScale = 0.55;
  const p = layout?.page;
  const paperBackground = useMemo(() => {
    if (settings.paperType === 'blanko') return '#fff';
    if (settings.paperType === 'liniert') {
      return 'repeating-linear-gradient(to bottom, #fff 0, #fff 24px, #d3e5ff 24px, #d3e5ff 25px)';
    }
    return 'repeating-linear-gradient(to bottom, #fff 0, #fff 24px, #dce8ff 24px, #dce8ff 25px), repeating-linear-gradient(to right, transparent 0, transparent 24px, #dce8ff 24px, #dce8ff 25px)';
  }, [settings.paperType]);

  const update = (key, value) => setSettings((s) => ({ ...s, [key]: value }));

  const exportPdf = async () => {
    const r = await fetch(`${API}/api/export/pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, settings })
    });
    const blob = await r.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'handschrift.pdf';
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div className="app">
      <h1>Handschrift-PDF Generator</h1>
      <div className="grid">
        <section className="panel">
          <label>Text</label>
          <textarea rows={14} value={text} onChange={(e) => setText(e.target.value)} />
          <div className="examples">
            {examples.map((ex, i) => <button key={i} onClick={() => setText(ex)}>Beispiel {i + 1}</button>)}
          </div>
          <div className="controls">
            <Sel label="Papier" value={settings.paperType} onChange={(v) => update('paperType', v)} opts={['liniert', 'kariert', 'blanko']} />
            <Sel label="Farbe" value={settings.penColor} onChange={(v) => update('penColor', v)} opts={['blau', 'schwarz']} />
            <Sel label="Stil" value={settings.stylePreset} onChange={(v) => update('stylePreset', v)} opts={['classic', 'neat', 'lively']} />
            <Num label="Schriftgröße" value={settings.fontSize} onChange={(v) => update('fontSize', +v)} />
            <Num label="Zeilenabstand" value={settings.lineHeight} onChange={(v) => update('lineHeight', +v)} />
            <Num label="Rand links (mm)" value={settings.marginLeftMm} onChange={(v) => update('marginLeftMm', +v)} />
            <Num label="Rand rechts (mm)" value={settings.marginRightMm} onChange={(v) => update('marginRightMm', +v)} />
            <Num label="Rand oben (mm)" value={settings.marginTopMm} onChange={(v) => update('marginTopMm', +v)} />
            <Num label="Rand unten (mm)" value={settings.marginBottomMm} onChange={(v) => update('marginBottomMm', +v)} />
            <Num label="Seed" value={settings.seed} onChange={(v) => update('seed', v)} />
            <Num label="Unsauberkeit 0-100" value={settings.messiness} onChange={(v) => update('messiness', +v)} min={0} max={100} />
          </div>
          <button className="export" onClick={exportPdf}>PDF exportieren</button>
        </section>

        <section className="previewWrap">
          <h3>Vorschau (max. 2 Seiten)</h3>
          {layout && p && layout.pages.map((pg, pi) => (
            <div
              key={pi}
              className="page"
              style={{ width: p.width * pageScale, height: p.height * pageScale, backgroundImage: paperBackground }}>
              {pg.lines.map((line, i) => line.runs.map((run, j) => (
                <span
                  key={`${i}-${j}`}
                  style={{
                    position: 'absolute',
                    left: run.x * pageScale,
                    top: (line.y + run.baselineJitter) * pageScale,
                    transform: `rotate(${run.rotate}deg)`,
                    fontSize: settings.fontSize * pageScale,
                    color: settings.penColor === 'blau' ? '#1b3fa8' : '#1a1a1a',
                    fontFamily: run.style === 'hw3' ? 'monospace' : run.style === 'hw2' ? 'serif' : 'sans-serif',
                    letterSpacing: `${run.charSpacing * pageScale}px`
                  }}>{run.text}</span>
              )))}
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}

function Sel({ label, value, onChange, opts }) {
  return <label>{label}<select value={value} onChange={(e) => onChange(e.target.value)}>{opts.map((o) => <option key={o}>{o}</option>)}</select></label>;
}

function Num({ label, value, onChange, min, max }) {
  return <label>{label}<input min={min} max={max} value={value} onChange={(e) => onChange(e.target.value)} /></label>;
}
