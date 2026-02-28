const MM_TO_PT = 72 / 25.4;

export const pageFormats = {
  A4: { width: 595.28, height: 841.89 }
};

const stylePresets = {
  classic: ['hw1', 'hw2', 'hw3'],
  neat: ['hw1', 'hw1', 'hw2'],
  lively: ['hw1', 'hw2', 'hw3', 'hw2']
};

export function makeRandom(seedInput) {
  const seed = String(seedInput || '42');
  let h = 1779033703 ^ seed.length;
  for (let i = 0; i < seed.length; i++) {
    h = Math.imul(h ^ seed.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  return () => {
    h = Math.imul(h ^ (h >>> 16), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    h ^= h >>> 16;
    return (h >>> 0) / 4294967296;
  };
}

function parseParagraph(line) {
  const m = line.match(/^(\s*)([-•]|\d+\))\s+(.*)$/);
  if (!m) return { type: 'plain', marker: '', text: line };
  return { type: 'bullet', marker: m[2], text: m[3] };
}

function charWidth(ch, fontSize) {
  if (ch === ' ') return fontSize * 0.28;
  if ('ilI.,;:!|'.includes(ch)) return fontSize * 0.22;
  if ('mwMW@#'.includes(ch)) return fontSize * 0.75;
  return fontSize * 0.5;
}

function wordWidth(word, fontSize, spacing = 0) {
  return [...word].reduce((a, ch) => a + charWidth(ch, fontSize) + spacing, 0);
}

export function createLayout(text, settings, pageCountLimit = Infinity) {
  const page = pageFormats[settings.pageFormat] || pageFormats.A4;
  const margin = {
    left: settings.marginLeftMm * MM_TO_PT,
    right: settings.marginRightMm * MM_TO_PT,
    top: settings.marginTopMm * MM_TO_PT,
    bottom: settings.marginBottomMm * MM_TO_PT
  };

  const lineHeight = settings.lineHeight;
  const fontSize = settings.fontSize;
  const areaWidth = page.width - margin.left - margin.right;
  const areaHeight = page.height - margin.top - margin.bottom;

  const rand = makeRandom(settings.seed);
  const pages = [{ lines: [] }];
  let y = margin.top;

  const pushLine = (line) => {
    if (y + lineHeight > margin.top + areaHeight) {
      if (pages.length >= pageCountLimit) return false;
      pages.push({ lines: [] });
      y = margin.top;
    }
    line.y = y;
    pages.at(-1).lines.push(line);
    y += lineHeight;
    return true;
  };

  const lines = text.replace(/\r\n/g, '\n').split('\n');
  for (const rawLine of lines) {
    if (!rawLine.trim()) {
      if (!pushLine({ runs: [], type: 'blank' })) break;
      y += lineHeight * 0.25;
      continue;
    }

    const parsed = parseParagraph(rawLine);
    const markerCol = parsed.type === 'bullet' ? 18 : 0;
    const hangIndent = parsed.type === 'bullet' ? 22 : 0;
    const words = parsed.text.split(/\s+/).filter(Boolean);
    let row = [];
    let rowW = 0;

    for (const word of words) {
      const spacing = (rand() - 0.5) * 0.08 * (settings.messiness / 100);
      const w = wordWidth(word, fontSize, spacing);
      const space = row.length ? charWidth(' ', fontSize) : 0;
      const avail = areaWidth - (row.length === 0 ? markerCol + hangIndent : markerCol + hangIndent);
      if (rowW + space + w > avail && row.length) {
        if (!pushLine(makeLine(row, parsed, settings, rand, margin.left, markerCol, hangIndent, fontSize))) break;
        row = [];
        rowW = 0;
      }
      row.push({ word, spacing });
      rowW += (row.length > 1 ? space : 0) + w;
    }
    if (row.length) {
      if (!pushLine(makeLine(row, parsed, settings, rand, margin.left, markerCol, hangIndent, fontSize))) break;
    }
    y += lineHeight * 0.15;
  }

  return { pages, page, margin };
}

function makeLine(row, parsed, settings, rand, xBase, markerCol, hangIndent, fontSize) {
  const presets = stylePresets[settings.stylePreset] || stylePresets.classic;
  const runs = [];
  let x = xBase + markerCol + hangIndent;
  if (parsed.type === 'bullet') {
    runs.push({
      text: parsed.marker,
      x: xBase,
      style: 'hw2',
      baselineJitter: (rand() - 0.5) * 0.3,
      rotate: (rand() - 0.5) * 2,
      charSpacing: 0
    });
  }
  for (let i = 0; i < row.length; i++) {
    const item = row[i];
    const style = presets[Math.floor(rand() * presets.length)];
    const rotate = (rand() - 0.5) * 1.6 * (settings.messiness / 100);
    const baselineJitter = (rand() - 0.5) * 1.8 * (settings.messiness / 100);
    runs.push({
      text: item.word + (i < row.length - 1 ? ' ' : ''),
      x,
      style,
      baselineJitter,
      rotate,
      charSpacing: item.spacing
    });
    x += wordWidth(item.word + ' ', fontSize, item.spacing);
  }
  return { type: parsed.type, runs };
}
