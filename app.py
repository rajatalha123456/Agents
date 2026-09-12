"""
Contract Analyzer — Web UI (Flask)

Run:
    python app.py

Then open http://127.0.0.1:5000 in your browser, upload a .pdf/.docx contract,
and get the structured analysis rendered on screen.
"""

import os
import uuid
from flask import Flask, request, render_template, redirect, url_for, flash

from ingestion import extract_text, chunk_text
from extractor import analyze_contract_chunks, get_client

app = Flask(__name__)
app.secret_key = os.urandom(24)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".docx"}


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    file = request.files.get("contract")

    if not file or file.filename == "":
        flash("Choose a .pdf or .docx file first.")
        return redirect(url_for("index"))

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        flash(f"Unsupported file type '{ext}'. Upload a .pdf or .docx file.")
        return redirect(url_for("index"))

    # Save with a unique name to avoid collisions
    saved_name = f"{uuid.uuid4().hex}{ext}"
    saved_path = os.path.join(UPLOAD_DIR, saved_name)
    file.save(saved_path)

    try:
        text = extract_text(saved_path)
        if not text.strip():
            flash("No extractable text found. If this is a scanned PDF, it isn't supported yet.")
            return redirect(url_for("index"))

        chunks = chunk_text(text)
        client = get_client()
        result = analyze_contract_chunks(chunks, client)

        return render_template(
            "results.html",
            filename=file.filename,
            result=result,
        )

    except RuntimeError as e:
        # e.g. missing GEMINI_API_KEY
        flash(str(e))
        return redirect(url_for("index"))
    except Exception as e:
        flash(f"Something went wrong while analyzing: {e}")
        return redirect(url_for("index"))
    finally:
        # Clean up the uploaded file after analysis
        if os.path.exists(saved_path):
            os.remove(saved_path)


if __name__ == "__main__":
    app.run(debug=True, port=5000)