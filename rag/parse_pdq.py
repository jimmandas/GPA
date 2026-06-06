"""
Parse step of the RAG ingestion pipeline (ADR-019): NCI PDQ HTML -> section JSON.

This is the FIRST stage of parse -> chunk -> embed -> index. It fetches the
public-domain NCI PDQ NSCLC Treatment (Health Professional Version) HTML from
cancer.gov, extracts the clinical content with lxml (open source, BSD), segments
it by heading into sections, and writes rag/pdq_corpus/nsclc_hp.json (the frozen
corpus artifact consumed by rag/ingest_pdq.py).

Why HTML, not PDF: cancer.gov publishes structured HTML whose heading tags drive
section-aware chunking. PDF parsing flattens that structure and is lossier.

Why this exists as a committed module: so the FULL chain is reproducible from a
clean clone (parse -> chunk -> embed), not just chunk-onward from a pre-parsed JSON.

Determinism note (invariant 13): the committed nsclc_hp.json is the FROZEN corpus.
Re-running this fetches live source — if NCI updates the summary, the corpus changes
and must be followed by an index rebuild + eval re-run. The `retrieved` date stamps
when the fetch happened.

License (ADR-019): PDQ text is public domain ("content of PDQ documents can be used
freely as text"). Text-only extraction (images excluded). Not labeled as an official
NCI PDQ summary; attributed as source with the preferred citation.

Usage:
  PYTHONPATH=. python rag/parse_pdq.py                 # fetch live + write corpus
  PYTHONPATH=. python rag/parse_pdq.py --html FILE     # parse a local HTML file
  PYTHONPATH=. python rag/parse_pdq.py --out PATH       # custom output path
"""

import argparse
import json
import pathlib
import re
import urllib.request
from datetime import datetime, timezone

from lxml import html

SOURCE_URL = "https://www.cancer.gov/types/lung/hp/non-small-cell-lung-treatment-pdq"
OUT_PATH = pathlib.Path(__file__).parent / "pdq_corpus" / "nsclc_hp.json"

SOURCE_NAME = "NCI PDQ — Non-Small Cell Lung Cancer Treatment (Health Professional Version)"
LICENSE = (
    "Public domain (US Govt / NCI). 'The content of PDQ documents can be used freely "
    "as text.' Text-only; images excluded. Not labeled as an official NCI PDQ summary."
)
CITATION = (
    "PDQ Adult Treatment Editorial Board. PDQ Non-Small Cell Lung Cancer Treatment. "
    "Bethesda, MD: National Cancer Institute."
)
MIN_SECTION_CHARS = 200  # drop nav crumbs / tiny fragments


def fetch_html(url: str = SOURCE_URL) -> str:
    """Fetch the PDQ HTML. cancer.gov requires a User-Agent."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (GPA research POC)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_sections(html_text: str) -> list:
    """lxml extraction: <article> -> heading-segmented clinical sections (text only)."""
    root = html.fromstring(html_text)
    articles = root.xpath("//article")
    container = articles[0] if articles else root.xpath("//main")[0]

    # Drop non-content nodes (text-only; images/tables excluded per license + chunking).
    for bad in container.xpath(".//script | .//style | .//nav | .//figure | .//table"):
        bad.getparent().remove(bad)

    # Walk in document order, segmenting on h1-h3 headings.
    sections = []
    cur = {"heading": "PREAMBLE", "level": 0, "parts": []}
    for el in container.iter():
        tag = el.tag if isinstance(el.tag, str) else ""
        if tag in ("h1", "h2", "h3"):
            htext = (el.text_content() or "").strip()
            if htext:
                if cur["parts"]:
                    sections.append(cur)
                cur = {"heading": htext, "level": int(tag[1]), "parts": []}
        elif tag in ("p", "li"):
            t = (el.text_content() or "").strip()
            if t and len(t) > 1:
                cur["parts"].append(t)
    if cur["parts"]:
        sections.append(cur)

    # Assemble + drop tiny boilerplate sections.
    clean = []
    for s in sections:
        body = re.sub(r"\n{3,}", "\n\n", "\n".join(s["parts"]).strip())
        if len(body) >= MIN_SECTION_CHARS:
            clean.append({
                "heading": s["heading"],
                "level": s["level"],
                "text": body,
                "char_len": len(body),
            })
    return clean


def parse(html_text: str, retrieved: str) -> dict:
    """Build the provenance-tagged corpus dict from raw HTML."""
    sections = extract_sections(html_text)
    return {
        "source": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "license": LICENSE,
        "citation": CITATION,
        "retrieved": retrieved,
        "cancer_type": "nsclc",
        "sections": sections,
    }


def main():
    ap = argparse.ArgumentParser(description="Parse NCI PDQ NSCLC HTML -> corpus JSON")
    ap.add_argument("--html", help="parse a local HTML file instead of fetching live")
    ap.add_argument("--out", default=str(OUT_PATH), help="output JSON path")
    args = ap.parse_args()

    if args.html:
        print(f"Parsing local HTML: {args.html}")
        html_text = pathlib.Path(args.html).read_text(encoding="utf-8", errors="replace")
    else:
        print(f"Fetching {SOURCE_URL} ...")
        html_text = fetch_html()
        print(f"  fetched {len(html_text)} chars")

    retrieved = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    corpus = parse(html_text, retrieved)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(corpus, indent=2), encoding="utf-8")

    total = sum(s["char_len"] for s in corpus["sections"])
    print(f"✅ parsed {len(corpus['sections'])} sections ({total} chars) -> {out}")
    print(f"   source: public-domain NCI PDQ | retrieved {retrieved}")


if __name__ == "__main__":
    main()
