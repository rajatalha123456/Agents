"""Single durable worker: python -m app.large_data.

Detector state is bounded by batch rows AND cells. All findings are streamed to
disk; dashboard evidence is bounded. Baselines are explicitly batch-relative.
"""

import csv
import json
import logging
import os
import random
import re
import time
from collections import Counter
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from .routers import generic_anomaly as detector
from .routers import uploads

BATCH_ROWS = min(detector.MAX_ROWS, max(1, int(os.getenv("ANOMALY_BATCH_ROWS", "5000"))))
BATCH_CELLS = min(detector.MAX_CELLS, max(1, int(os.getenv("ANOMALY_BATCH_CELLS", "100000"))))
MAX_RECORD_BYTES = int(os.getenv("ANOMALY_MAX_RECORD_BYTES", str(4 * 1024**2)))
MAX_COLUMNS = 2000
NOTICE = ("Batch-relative analysis: every row was processed, but statistical baselines, "
          "duplicates, rarity and relationships are evaluated within each batch. "
          "Cross-batch anomalies can be missed. Charts are sampled; download all findings for complete evidence.")


def iter_rows(path, filename):
    suffix = filename.lower().rsplit(".", 1)[-1]
    if suffix == "csv":
        csv.field_size_limit(MAX_RECORD_BYTES)
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = detector._csv_reader(stream)
            if not reader.fieldnames or len(reader.fieldnames) > MAX_COLUMNS or len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise ValueError("CSV requires distinct headers, with at most 2,000 columns.")
            for row in reader:
                if None in row:
                    raise ValueError("CSV row contains more values than its header.")
                yield row
    elif suffix in {"jsonl", "ndjson"}:
        with path.open("rb") as stream:
            while True:
                line = stream.readline(MAX_RECORD_BYTES + 1)
                if not line:
                    break
                if len(line) > MAX_RECORD_BYTES:
                    raise ValueError("A JSONL record exceeds the configured record size.")
                if line.strip():
                    item = json.loads(line.decode("utf-8-sig"))
                    if not isinstance(item, dict):
                        raise ValueError("Every JSONL record must be an object.")
                    yield detector._flatten(item)
    else:
        import ijson
        # Large JSON supports an array or a conventional wrapper array.
        # Inspect parser events without constructing the surrounding object.
        with path.open("rb") as stream:
            prefix = None
            for name, event, value in ijson.parse(stream):
                if event == "start_array" and name in {"", "data", "rows", "records", "items"}:
                    prefix = f"{name}.item" if name else "item"
                    break
                if name == "" and event not in {"start_map", "map_key"}:
                    break
            if prefix is None:
                raise ValueError("Large JSON requires an array of objects, or a data/rows/records/items array. Use JSONL for individual records.")
            stream.seek(0)
            for item in ijson.items(stream, prefix, use_float=True):
                if not isinstance(item, dict):
                    raise ValueError("Every JSON array record must be an object.")
                yield detector._flatten(item)


def batches(path, filename):
    batch, cells, byte_count = [], 0, 0
    for row in iter_rows(path, filename):
        size = len(json.dumps(row, ensure_ascii=True).encode("utf-8"))
        if size > MAX_RECORD_BYTES or len(row) > min(MAX_COLUMNS, BATCH_CELLS):
            raise ValueError("A record exceeds the configured record size or column capacity.")
        if batch and (len(batch) >= BATCH_ROWS or cells + len(row) > BATCH_CELLS or byte_count + size > 16 * 1024**2):
            yield batch
            batch, cells, byte_count = [], 0, 0
        batch.append(row)
        cells += len(row)
        byte_count += size
    if batch:
        yield batch


class Sample:
    def __init__(self, limit):
        self.limit, self.seen, self.items = limit, 0, []
        self.random = random.Random(42)

    def add(self, item):
        self.seen += 1
        if len(self.items) < self.limit:
            self.items.append(item)
        else:
            index = self.random.randrange(self.seen)
            if index < self.limit:
                self.items[index] = item


def remap_report(report, offset, batch_number):
    for item in report["anomalies"]:
        item["id"] = f"B{batch_number}-{item['id']}"
        item["batch"] = batch_number
        item["batch_start_row"] = offset + 1
        item["batch_end_row"] = offset + report["row_count"]
        if item.get("row"):
            item["row"] += offset
            item["message"] = re.sub(r"\bRow (\d+)\b", lambda m: f"Row {int(m[1]) + offset}", item["message"])
    for key in ("row_findings", "score_points", "preview_rows", "prepared_preview_rows"):
        for item in report[key]:
            item["row"] += offset
    for example in report["preprocessing"]["examples"]:
        example["row"] += offset
    for plot in report["numeric_plots"]:
        for point in plot["points"]:
            point["row"] += offset
    report["row_snapshots"] = {str(int(key) + offset): {**item, "row": item["row"] + offset}
                               for key, item in report["row_snapshots"].items()}


def update_job(job_id, **fields):
    with uploads.database() as db:
        db.execute(f"UPDATE jobs SET {','.join(key + '=?' for key in fields)},updated=? WHERE id=?",
                   (*fields.values(), time.time(), job_id))


class Cancelled(Exception):
    pass


def check_cancel(job_id):
    with uploads.database() as db:
        if uploads.get_job(db, job_id)["state"] == "cancelling":
            raise Cancelled()


def process_job(job):
    job_id = job["id"]
    directory = uploads.job_dir(job_id)
    partial = directory / "findings.partial"
    total_rows, batch_count = 0, 0
    totals, drivers, layers = Counter(), Counter(), Counter()
    models, column_names = {}, set()
    top, top_rows, snapshots = [], [], {}
    scores, plots = Sample(1000), {}
    statistical_rows, flagged_evidence = Sample(2000), Sample(200)
    statistical_columns = []
    preparation_counts, preparation_totals = Counter(), Counter()
    preparation_columns, preparation_examples = {}, []
    template = None
    with partial.open("w", encoding="utf-8") as output:
        for batch in batches(directory / "source", job["filename"]):
            check_cancel(job_id)
            report = detector.analyze_rows(batch, include_all=True, call_ai=False)
            prepared_batch = report.pop("_prepared_rows")
            column_names.update(column["name"] for column in report["columns"])
            if len(column_names) > MAX_COLUMNS:
                raise ValueError("Dataset contains more than 2,000 distinct columns.")
            for model in report["model_inventory"]:
                state = models.setdefault(model["id"], {**model, "detections": 0, "max_score": 0, "confidence_sum": 0})
                state["detections"] += model["detections"]
                state["max_score"] = max(state["max_score"], model["max_score"])
                state["confidence_sum"] += model["average_confidence"] * model["detections"]
            batch_count += 1
            remap_report(report, total_rows, batch_count)
            total_rows += len(batch)
            preparation = report["preprocessing"]
            preparation_counts.update(preparation["counts"])
            for key in ("input_rows", "output_rows", "total_cells", "eligible_cells", "unavailable_cells", "duplicate_extra_rows", "duplicate_groups"):
                preparation_totals[key] += preparation[key]
            preparation_examples = (preparation_examples + preparation["examples"])[:40]
            for column in preparation["columns"]:
                state = preparation_columns.setdefault(column["name"], {**column, "counts": Counter(), "eligible_batches": 0})
                state["counts"].update(column["counts"])
                state["eligible_batches"] += int(column["model_eligible"])
                state["model_eligible"] = bool(state["eligible_batches"])
            if template is None:
                template = report.copy()
                template["profile_scope"] = "First batch only; numeric charts combine sampled points from all batches."
                template["risk_distribution"] = [{**band, "count": 0} for band in report["risk_distribution"]]
                statistical_columns = [column["name"] for column in report["columns"] if column["type"] == "numeric"][:8]
            flagged = {a["row"] for a in report["anomalies"] if a.get("row")}
            for row_number, row in enumerate(prepared_batch, total_rows - len(batch) + 1):
                point = {"row": row_number, "flagged": row_number in flagged,
                         "values": {name: detector._coerce_number(row.get(name)) for name in statistical_columns}}
                statistical_rows.add(point)
                if point["flagged"]:
                    flagged_evidence.add(point)
            for anomaly in report["anomalies"]:
                output.write(json.dumps(anomaly, ensure_ascii=True) + "\n")
                drivers[anomaly["type"]] += 1
                layers[anomaly["layer"]] += 1
            for key in ("total_anomalies", "critical", "high", "medium", "low"):
                totals[key] += report["summary"][key]
            totals["max_risk_score"] = max(totals["max_risk_score"], report["summary"]["max_risk_score"])
            for target, band in zip(template["risk_distribution"], report["risk_distribution"]):
                target["count"] += band["count"]
            top = sorted(top + report["anomalies"], key=lambda a: (-a["score"], a["row"] or 0))[:300]
            top_rows = sorted(top_rows + report["row_findings"], key=lambda a: -a["score"])[:50]
            snapshots.update(report["row_snapshots"])
            kept = {str(item["row"]) for item in top + top_rows if item.get("row")}
            snapshots = {key: value for key, value in snapshots.items() if key in kept}
            for point in report["score_points"]:
                scores.add(point)
            for plot in report["numeric_plots"]:
                name = plot["column"]
                if name not in plots and len(plots) >= 8:
                    continue
                state = plots.setdefault(name, {"column": name, "total": 0, "outlier_count": 0,
                                               "normal": Sample(600), "outliers": Sample(400)})
                state["total"] += plot["total"]
                state["outlier_count"] += plot["outlier_count"]
                for point in plot["points"]:
                    state["outliers" if point["outlier"] else "normal"].add(point)
            output.flush()
            update_job(job_id, rows_done=total_rows, batches_done=batch_count)
            # Do not retain a full first-batch report through the whole job.
            if batch_count == 1:
                template.update(anomalies=[], row_snapshots={}, row_findings=[], numeric_plots=[], score_points=[])
    check_cancel(job_id)
    if template is None:
        raise ValueError("No records found in this file.")
    summary = dict(totals)
    quality_score = round(100 * (1 - preparation_totals["unavailable_cells"] / preparation_totals["eligible_cells"]), 2) if preparation_totals["eligible_cells"] else None
    summary.update(shown_anomalies=len(top), data_quality_score=quality_score)
    template["preprocessing"] = {**template["preprocessing"], **dict(preparation_totals),
                                 "scope": "batch", "cell_quality_score": quality_score,
                                 "counts": dict(preparation_counts), "examples": preparation_examples,
                                 "columns": [{**c, "counts": dict(c["counts"])} for c in preparation_columns.values()]}
    template.update(
        analysis_id=job_id, filename=job["filename"], file_type=job["filename"].rsplit(".", 1)[-1],
        created_at=datetime.now(timezone.utc).isoformat(), row_count=total_rows, column_count=len(column_names),
        anomalies=top, row_findings=top_rows, row_snapshots=snapshots, summary=summary,
        score_points=sorted(scores.items, key=lambda p: p["row"]),
        numeric_plots=[{"column": p["column"], "total": p["total"], "outlier_count": p["outlier_count"],
                        "scope": "batch", "points": p["normal"].items + p["outliers"].items} for p in plots.values()],
        severity_distribution=detector._severity_distribution(summary),
        driver_breakdown=[{"type": key, "label": key.replace("_", " "), "count": count} for key, count in drivers.most_common(8)],
        processing={"mode": "batch", "batches": batch_count, "batch_rows": BATCH_ROWS, "notice": NOTICE},
        analyst_summary=[f"{total_rows:,} rows processed in {batch_count:,} batches.",
                         f"{totals['total_anomalies']:,} findings; the dashboard retains the top {len(top)}.", NOTICE],
        decision=detector._model_decision(summary),
        statistical_graphs=detector._statistical_graphs(
            statistical_rows.items, statistical_columns, total_rows=total_rows,
            scope="reservoir" if total_rows > len(statistical_rows.items) else "dataset",
            extra_points=flagged_evidence.items),
    )
    for layer in template["layers"]:
        layer["count"] = layers[layer["id"]]
    template["model_inventory"] = [{**model, "active": bool(model["detections"]),
                                    "average_confidence": round(model["confidence_sum"] / model["detections"], 2) if model["detections"] else 0}
                                   for model in models.values()]
    template["model_card"]["training"] = "Independent per-batch baselines; no global fit."
    template["model_card"]["limitations"] += " " + NOTICE
    template["model_card"]["active_model_count"] = sum(m["active"] for m in template["model_inventory"])
    # Publish only complete reports, then remove the large raw source.
    partial.replace(directory / "findings.jsonl")
    detector._save_analysis(template)
    with uploads.database() as db:
        db.execute("BEGIN IMMEDIATE")
        if uploads.get_job(db, job_id)["state"] == "cancelling":
            raise Cancelled()
        db.execute("UPDATE jobs SET state='completed',updated=? WHERE id=?", (time.time(), job_id))
    (directory / "source").unlink(missing_ok=True)


def run_once():
    with uploads.database() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
        if row is None:
            return False
        job = dict(row)
        db.execute("UPDATE jobs SET state='processing',error=NULL,rows_done=0,batches_done=0,updated=? WHERE id=?",
                   (time.time(), job["id"]))
    try:
        process_job(job)
    except Cancelled:
        update_job(job["id"], state="cancelled")
    except Exception as exc:
        logging.exception("Large analysis failed: %s", job["id"])
        update_job(job["id"], state="failed", error=f"Analysis stopped: {str(exc)[:400]}")
    finally:
        with uploads.database() as db:
            state = uploads.get_job(db, job["id"])["state"]
        if state == "cancelled":
            for name in ("source", "findings.partial", "findings.jsonl"):
                (uploads.job_dir(job["id"]) / name).unlink(missing_ok=True)
            detector._analysis_path(job["id"]).unlink(missing_ok=True)
    return True


def recover_interrupted_jobs():
    with uploads.database() as db:
        # Interrupted jobs restart from disk; partial evidence is overwritten.
        db.execute("UPDATE jobs SET state='queued' WHERE state='processing'")
        cancelled = db.execute("SELECT id FROM jobs WHERE state='cancelling'").fetchall()
        for row in cancelled:
            for name in ("source", "findings.partial", "findings.jsonl"):
                (uploads.job_dir(row["id"]) / name).unlink(missing_ok=True)
            detector._analysis_path(row["id"]).unlink(missing_ok=True)
        db.execute("UPDATE jobs SET state='cancelled' WHERE state='cancelling'")


def main():
    # One worker per data directory. OS lock is released even after a crash.
    uploads.DATA_DIR.mkdir(parents=True, exist_ok=True)
    lock = (uploads.DATA_DIR / "worker.lock").open("a+b")
    lock.write(b"0")
    lock.flush()
    lock.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    recover_interrupted_jobs()
    while True:
        if not run_once():
            time.sleep(2)


if __name__ == "__main__":
    main()
