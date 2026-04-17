"""Optionale KI-Strukturierung via Anthropic Claude API.

Aktiviert mit HEFTERPRO_AI=1 und ANTHROPIC_API_KEY in der Umgebung.
Fällt bei Fehlern lautlos auf die heuristische Strukturierung zurück.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def _get_client():
    try:
        import anthropic
    except ImportError:
        log.info("anthropic Paket nicht installiert — KI deaktiviert.")
        return None
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        log.info("ANTHROPIC_API_KEY nicht gesetzt — KI deaktiviert.")
        return None
    return anthropic.Anthropic(api_key=key)


def enhance(
    title: str,
    sections: List[Any],
) -> Optional[Dict]:
    client = _get_client()
    if client is None:
        return None

    sections_text = []
    for s in sections:
        sec = s if isinstance(s, dict) else s.model_dump()
        parts = [f"## {sec['heading']}"]
        for b in sec.get("body", []):
            parts.append(b)
        for bullet in sec.get("bullets", []):
            parts.append(f"- {bullet}")
        if sec.get("callout"):
            parts.append(f"[Merke: {sec['callout']}]")
        sections_text.append("\n".join(parts))

    content_block = f"# {title}\n\n" + "\n\n".join(sections_text)

    prompt = f"""Du bist ein Experte für die Erstellung von Lernmaterialien für deutsche Schüler.

Gegeben ist ein vorstrukturiertes Hefterblatt. Deine Aufgabe:
1. Verbessere den Titel (kurz, prägnant, schülerfreundlich)
2. Strukturiere die Abschnitte klar und logisch
3. Formuliere Stichpunkte knapp und einprägsam
4. Wähle die wichtigste Aussage als "Merke"-Box pro Abschnitt
5. Maximal 5 Abschnitte, maximal 6 Stichpunkte pro Abschnitt

Antworte NUR mit validem JSON in diesem Format:
{{
  "title": "Verbesserter Titel",
  "sections": [
    {{
      "heading": "Abschnittsüberschrift",
      "body": ["Optionaler Fließtext"],
      "bullets": ["Stichpunkt 1", "Stichpunkt 2"],
      "callout": "Wichtigste Erkenntnis oder null"
    }}
  ]
}}

Inhalt:
{content_block}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
        return json.loads(text)
    except Exception as exc:
        log.warning("KI-Strukturierung fehlgeschlagen: %s", exc)
        return None
