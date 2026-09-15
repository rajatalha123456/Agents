"""
Contract Analyzer — CLI entry point.

Usage:
    python main.py path/to/contract.pdf
    python main.py path/to/contract.docx --out report.json
"""

import argparse
import json
import sys

from ingestion import extract_text, chunk_text
from extractor import analyze_contract_chunks, get_client


def run(file_path: str, out_path: str = None):
    print(f"[1/3] Extracting text from {file_path} ...")
    text = extract_text(file_path)

    if not text.strip():
        print("ERROR: No extractable text found. If this is a scanned PDF, add OCR to ingestion.py.")
        sys.exit(1)

    print(f"[2/3] Chunking ({len(text)} chars) ...")
    chunks = chunk_text(text)
    print(f"      -> {len(chunks)} chunk(s)")

    print("[3/3] Running Gemini analysis ...")
    client = get_client()
    result = analyze_contract_chunks(chunks, client)

    report = result.model_dump_json(indent=2)

    out_path = out_path or (file_path.rsplit(".", 1)[0] + "_analysis.json")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\nDone. Report saved to: {out_path}")
    print("\n--- Summary ---")
    print(f"Contract type   : {result.contract_type} (confidence: {result.contract_type_confidence})")
    print(f"PSR applicable  : {result.psr.applicable}")
    print(f"Fees found      : {len(result.fees)}")
    print(f"Loss clauses    : {len(result.loss_clauses)}")
    print(f"Dates found     : {len(result.dates)}")
    print(f"Conflicts found : {len(result.conflicts)}")
    print(f"Needs review    : {result.needs_human_review}")
    if result.review_notes:
        print(f"Review notes    : {result.review_notes}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze a contract file with the Contract Analyzer agent.")
    parser.add_argument("file", help="Path to a .pdf or .docx contract file")
    parser.add_argument("--out", help="Output JSON path (default: <file>_analysis.json)", default=None)
    args = parser.parse_args()

    run(args.file, args.out)