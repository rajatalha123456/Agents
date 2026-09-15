import csv
import io
import json
import math
import os
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
from .. import preprocessing

router = APIRouter()

ANALYSES: dict[str, dict[str, Any]] = {}
MAX_ROWS = 100000
MAX_CELLS = 2000000
MAX_UPLOAD_BYTES = 64 * 1024 * 1024
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
STORAGE_DIR = Path(os.environ.get("ANOMALY_STORAGE_DIR", ".data/anomaly_analyses"))


class AnomalyChatRequest(BaseModel):
    message: str
    history: list[dict[str, str]] = []


def _storage_dir() -> Path:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return STORAGE_DIR


def _analysis_path(analysis_id: str) -> Path:
    if not analysis_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for char in analysis_id):
        raise HTTPException(status_code=400, detail="Invalid analysis id.")
    return _storage_dir() / f"{analysis_id}.json"


def _save_analysis(result: dict[str, Any]) -> None:
    path = _analysis_path(result["analysis_id"])
    temporary = path.with_suffix(f".{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=True), encoding="utf-8")
    temporary.replace(path)


def _load_analysis(analysis_id: str) -> dict[str, Any] | None:
    if analysis_id in ANALYSES:
        return ANALYSES[analysis_id]
    path = _analysis_path(analysis_id)
    if not path.exists():
        return None
    result = json.loads(path.read_text(encoding="utf-8"))
    ANALYSES[analysis_id] = result
    return result


def _history_item(result: dict[str, Any]) -> dict[str, Any]:
    summary = result.get("summary", {})
    return {
        "analysis_id": result.get("analysis_id"),
        "filename": result.get("filename"),
        "file_type": result.get("file_type"),
        "created_at": result.get("created_at"),
        "row_count": result.get("row_count", 0),
        "column_count": result.get("column_count", 0),
        "decision": result.get("decision", {}),
        "total_anomalies": summary.get("total_anomalies", 0),
        "max_risk_score": summary.get("max_risk_score", 0),
    }


def _list_saved_analyses(limit: int = 25) -> list[dict[str, Any]]:
    items = []
    for path in _storage_dir().glob("*.json"):
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items.append(_history_item(result))
    return sorted(items, key=lambda item: item.get("created_at") or "", reverse=True)[:limit]


def _looks_like_identifier(column: str, unique_rate: float) -> bool:
    normalized = column.lower().replace(" ", "_").replace("-", "_")
    id_names = {"id", "row_id", "record_id", "serial", "serial_no", "s_no", "index"}
    return unique_rate >= 0.9 and (normalized in id_names or normalized.endswith("_id") or normalized.endswith("id"))


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            out.update(_flatten(item, f"{prefix}.{key}" if prefix else str(key)))
        return out
    if isinstance(value, list):
        return {prefix: json.dumps(value, ensure_ascii=True)}
    return {prefix: value}


def _json_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        if any(not isinstance(item, dict) for item in payload):
            raise HTTPException(status_code=400, detail="Every JSON record must be an object; no records were discarded.")
        return [_flatten(item) for item in payload]
    if isinstance(payload, dict):
        for key in ("data", "rows", "records", "items"):
            if isinstance(payload.get(key), list):
                return _json_rows(payload[key])
        return [_flatten(payload)]
    raise HTTPException(status_code=400, detail="JSON must be an object or an array of objects.")


def _csv_reader(stream):
    """Recognize common CSV separators without consuming the source stream."""
    position = stream.tell()
    sample = stream.read(65536)
    stream.seek(position)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        # The sample can end inside a record. Retry the header before defaulting
        # to comma for a single-column file.
        try:
            dialect = csv.Sniffer().sniff(sample.splitlines()[0], delimiters=",;\t|")
        except (csv.Error, IndexError):
            dialect = csv.excel
    reader = csv.DictReader(stream, dialect=dialect, strict=True)
    headers = [name.strip().lstrip("\ufeff") for name in reader.fieldnames or []]
    if not headers or any(not name for name in headers) or len(headers) != len(set(headers)):
        raise csv.Error("CSV requires distinct, non-empty headers after normalization.")
    return reader


def _coerce_number(value: Any) -> float | None:
    return preprocessing.parse_number(value)


def _is_date(value: Any) -> bool:
    if not value:
        return False
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            datetime.strptime(text[:10], fmt)
            return True
        except ValueError:
            pass
    return False


def _quantile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def _severity(score: float) -> str:
    if score >= 85:
        return "critical"
    if score >= 65:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _confidence(score: float) -> float:
    return min(0.99, max(0.55, 0.5 + score / 200))


def _empty(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _profile_columns(rows: list[dict[str, Any]]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    columns = sorted({key for row in rows for key in row.keys()})
    profiles: dict[str, dict[str, Any]] = {}
    total = len(rows)

    for column in columns:
        values = [row.get(column) for row in rows]
        present = [value for value in values if not _empty(value)]
        numeric = [_coerce_number(value) for value in present]
        numeric = [value for value in numeric if value is not None]
        numeric_ratio = len(numeric) / len(present) if present else 0
        counts = Counter(str(value).strip() for value in present)
        date_count = sum(count for value, count in counts.items() if _is_date(value)) if numeric_ratio < 0.75 else 0
        date_ratio = date_count / len(present) if present else 0
        unique_rate = len(counts) / len(present) if present else 0
        kind = "numeric" if numeric_ratio >= 0.75 else "date" if date_ratio >= 0.75 else "category"
        if _looks_like_identifier(column, unique_rate):
            kind = "identifier"
        profile: dict[str, Any] = {
            "name": column,
            "type": kind,
            "missing": total - len(present),
            "missing_rate": round((total - len(present)) / total, 4) if total else 0,
            "unique": len(counts),
            "unique_rate": round(unique_rate, 4),
            "top_values": counts.most_common(5),
        }

        if kind == "numeric" and numeric:
            avg = sum(numeric) / len(numeric)
            med = median(numeric)
            deviations = [abs(value - med) for value in numeric]
            mad = median(deviations) or 0.0
            std = math.sqrt(sum((value - avg) ** 2 for value in numeric) / len(numeric)) if len(numeric) > 1 else 0.0
            q1 = _quantile(numeric, 0.25)
            q3 = _quantile(numeric, 0.75)
            profile.update({
                "min": min(numeric),
                "max": max(numeric),
                "mean": round(avg, 4),
                "median": round(med, 4),
                "std": round(std, 4),
                "mad": round(mad, 4),
                "q1": q1,
                "q3": q3,
                "iqr": q3 - q1,
            })
        profiles[column] = profile
    return columns, profiles


def _add_anomaly(anomalies: list[dict[str, Any]], item: dict[str, Any]):
    item["id"] = f"A-{len(anomalies) + 1:04d}"
    item["confidence"] = round(_confidence(item["score"]), 2)
    item["severity"] = _severity(item["score"])
    anomalies.append(item)


def _numeric_signal(value: float, profile: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
    med = float(profile.get("median") or 0)
    mad = float(profile.get("mad") or 0)
    mean = float(profile.get("mean") or 0)
    std = float(profile.get("std") or 0)
    iqr = float(profile.get("iqr") or 0)
    q1 = float(profile.get("q1") or 0)
    q3 = float(profile.get("q3") or 0)

    robust_z = abs(0.6745 * (value - med) / mad) if mad else 0
    z_score = abs((value - mean) / std) if std else 0
    fence_hit = iqr > 0 and (value < q1 - 1.5 * iqr or value > q3 + 1.5 * iqr)
    raw = max(robust_z, z_score, 3.0 if fence_hit else 0)
    score = min(100, raw * 18)
    contributions = [
        {"feature": profile["name"], "impact": round(score, 1), "reason": f"value {value:g} vs median {med:g}"},
    ]
    if robust_z:
        contributions.append({"feature": "robust_z", "impact": round(min(100, robust_z * 18), 1), "reason": f"robust z-score {robust_z:.2f}"})
    if fence_hit:
        contributions.append({"feature": "iqr_fence", "impact": 54, "reason": "outside 1.5x IQR fence"})
    return score, contributions


def _histogram(values: list[float], bins: int = 8) -> list[dict[str, Any]]:
    if not values:
        return []
    low = min(values)
    high = max(values)
    if low == high:
        return [{"from": low, "to": high, "count": len(values)}]
    width = (high - low) / bins
    buckets = [{"from": low + width * i, "to": low + width * (i + 1), "count": 0} for i in range(bins)]
    for value in values:
        index = min(bins - 1, int((value - low) / width))
        buckets[index]["count"] += 1
    return [
        {"from": round(bucket["from"], 4), "to": round(bucket["to"], 4), "count": bucket["count"]}
        for bucket in buckets
    ]


def _numeric_plots(rows, profiles):
    plots = []
    for name, profile in profiles.items():
        if profile["type"] != "numeric" or not profile.get("model_eligible", True) or "median" not in profile:
            continue
        normal, outliers = [], []
        for index, row in enumerate(rows, 1):
            value = _coerce_number(row.get(name))
            if value is None:
                continue
            score, _ = _numeric_signal(value, profile)
            (outliers if score >= 40 else normal).append({"row": index, "value": value, "outlier": score >= 40})
        plots.append({"column": name, "median": profile["median"],
                      "lower": profile["q1"] - 1.5 * profile["iqr"],
                      "upper": profile["q3"] + 1.5 * profile["iqr"],
                      "total": len(normal) + len(outliers), "outlier_count": len(outliers),
                      "points": normal[::max(1, math.ceil(len(normal) / 600))] + outliers[::max(1, math.ceil(len(outliers) / 400))]})
        if len(plots) == 8:
            break
    return plots


def _preview_rows(rows: list[dict[str, Any]], columns: list[str], limit: int = 10) -> list[dict[str, Any]]:
    preview = []
    for index, row in enumerate(rows[:limit], start=1):
        preview.append({
            "row": index,
            "values": {column: row.get(column) for column in columns[:12]},
        })
    return preview


def _statistical_graphs(records, columns, *, total_rows=None, scope="dataset", extra_points=()):
    """Descriptive IQR statistics; model flags remain separate scatter evidence.

    Records contain numeric values, original row numbers and existing model flags.
    Bulk callers provide a uniform reservoir across all rows, not the first batch.
    Extra flagged points are for scatter evidence only and never bias statistics.
    """
    summaries = []
    for column in columns[:8]:
        values = [r["values"][column] for r in records if r["values"].get(column) is not None]
        if not values:
            continue
        q1, q3 = _quantile(values, .25), _quantile(values, .75)
        med = median(values)
        lower, upper = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
        inside = [v for v in values if lower <= v <= upper]
        outside = [v for v in values if v < lower or v > upper]
        low, high = min(values), max(values)
        bins = 1 if low == high else 16
        width = (high - low) / bins if bins > 1 else 1
        histogram = [{"from": low + i * width if bins > 1 else low,
                      "to": low + (i + 1) * width if bins > 1 else high,
                      "normal": 0, "outliers": 0} for i in range(bins)]
        for value in values:
            index = min(bins - 1, max(0, int((value - low) / width)))
            histogram[index]["outliers" if value < lower or value > upper else "normal"] += 1
        summaries.append({"column": column, "count": len(values), "min": low, "max": high,
                          "q1": q1, "median": med, "q3": q3, "lower": lower, "upper": upper,
                          "whisker_low": min(inside, default=q1), "whisker_high": max(inside, default=q3),
                          "outlier_count": len(outside), "histogram": histogram,
                          "outlier_values": outside[::max(1, math.ceil(len(outside) / 200))]})
    names = [item["column"] for item in summaries]
    correlations = []
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            pairs = [(r["values"][left], r["values"][right]) for r in records
                     if r["values"].get(left) is not None and r["values"].get(right) is not None]
            xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
            defined = len(pairs) >= 3 and min(xs) != max(xs) and min(ys) != max(ys)
            correlations.append({"x": left, "y": right, "count": len(pairs),
                                 "r": round(_pearson(xs, ys), 4) if defined else None})
    normal = [r for r in records if not r["flagged"]]
    flagged = list({r["row"]: r for r in [*records, *extra_points] if r["flagged"]}.values())
    points = normal[::max(1, math.ceil(len(normal) / 600))] + flagged[::max(1, math.ceil(len(flagged) / 200))]
    return {"scope": scope, "total_rows": total_rows if total_rows is not None else len(records),
            "statistics_rows": len(records), "columns": summaries, "correlations": correlations,
            "points": points, "extra_flagged_evidence": bool(extra_points)}


def _risk_distribution(row_findings: list[dict[str, Any]], row_count: int) -> list[dict[str, Any]]:
    bands = [
        {"label": "0-34", "from": 0, "to": 34, "count": max(0, row_count - len(row_findings))},
        {"label": "35-54", "from": 35, "to": 54, "count": 0},
        {"label": "55-64", "from": 55, "to": 64, "count": 0},
        {"label": "65-84", "from": 65, "to": 84, "count": 0},
        {"label": "85-100", "from": 85, "to": 100, "count": 0},
    ]
    for finding in row_findings:
        score = finding["score"]
        for band in bands:
            if band["from"] <= score < band["to"] + 1:
                band["count"] += 1
                break
    return bands


def _severity_distribution(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"label": "Critical", "severity": "critical", "count": summary["critical"]},
        {"label": "High", "severity": "high", "count": summary["high"]},
        {"label": "Medium", "severity": "medium", "count": summary["medium"]},
        {"label": "Low", "severity": "low", "count": summary["low"]},
    ]


def _compact_row(row: dict[str, Any], columns: list[str], limit: int = 18) -> dict[str, Any]:
    return {column: row.get(column) for column in columns[:limit]}


def _chart_evidence(
    rows: list[dict[str, Any]],
    columns: list[str],
    anomalies: list[dict[str, Any]],
    row_findings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    anomalies_by_row: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for anomaly in anomalies:
        if anomaly.get("row"):
            anomalies_by_row[int(anomaly["row"])].append(anomaly)

    row_score_lookup = {finding["row"]: finding for finding in row_findings}
    row_snapshots: dict[str, dict[str, Any]] = {}
    score_points = []

    for row_number in range(1, len(rows) + 1):
        finding = row_score_lookup.get(row_number, {})
        row_anomalies = anomalies_by_row.get(row_number, [])
        layer_scores: dict[str, float] = defaultdict(float)
        for anomaly in row_anomalies:
            layer_scores[anomaly["layer"]] += float(anomaly["score"] or 0)
        dominant_layer = max(layer_scores.items(), key=lambda item: item[1])[0] if layer_scores else "none"
        score = round(float(finding.get("score") or 0), 1)
        score_points.append({
            "row": row_number,
            "score": score,
            "severity": _severity(score),
            "dominant_layer": dominant_layer,
            "anomaly_count": len(row_anomalies),
        })
        if row_anomalies or score >= 35:
            row_snapshots[str(row_number)] = {
                "row": row_number,
                "score": score,
                "severity": _severity(score),
                "values": _compact_row(rows[row_number - 1], columns),
                "reasons": finding.get("reasons", [])[:8],
                "layer_scores": {layer: round(value, 1) for layer, value in sorted(layer_scores.items())},
            }

    driver_breakdown = [
        {"type": reason, "label": reason.replace("_", " "), "count": count}
        for reason, count in Counter(item["type"] for item in anomalies).most_common(8)
    ]
    return score_points[::max(1, math.ceil(len(score_points) / 1000))], driver_breakdown, row_snapshots


def _model_inventory(anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    catalog = [
        {
            "id": "data_contract_rule",
            "name": "Data contract rule",
            "family": "statistical rule",
            "layer": "L1",
            "detects": "duplicate records and high missingness",
            "confidence_basis": "deterministic rule confidence from severity score",
        },
        {
            "id": "schema_inference_rule",
            "name": "Schema inference rule",
            "family": "statistical rule",
            "layer": "L1",
            "detects": "values that do not match inferred column type",
            "confidence_basis": "column type consistency and anomaly score",
        },
        {
            "id": "robust_outlier_model",
            "name": "Robust outlier model",
            "family": "statistical model",
            "layer": "L2",
            "detects": "numeric values far from normal file baseline",
            "confidence_basis": "MAD robust z-score, standard z-score, and IQR fence agreement",
        },
        {
            "id": "ratio_consistency_model",
            "name": "Ratio consistency model",
            "family": "statistical relationship model",
            "layer": "L2",
            "detects": "broken numeric ratios between two columns",
            "confidence_basis": "robust z-score against learned ratio baseline",
        },
        {
            "id": "correlation_residual_model",
            "name": "Correlation residual model",
            "family": "statistical relationship model",
            "layer": "L2",
            "detects": "rows that break a strong linear relationship",
            "confidence_basis": "residual distance from learned correlation line",
        },
        {
            "id": "knn_distance_model",
            "name": "K-nearest-neighbor distance model",
            "family": "unsupervised ML model",
            "layer": "L2",
            "detects": "rows far from nearest similar rows across numeric features",
            "confidence_basis": "top 5% robust scaled distance plus z-score",
        },
        {
            "id": "frequency_rarity_model",
            "name": "Frequency rarity model",
            "family": "statistical pattern model",
            "layer": "L3",
            "detects": "rare categorical labels",
            "confidence_basis": "frequency, unique-rate, and sample size",
        },
        {
            "id": "cross_column_pattern_model",
            "name": "Cross-column pattern model",
            "family": "statistical pattern model",
            "layer": "L3",
            "detects": "unusual categorical combinations after noise guards",
            "confidence_basis": "pair frequency while individual values repeat",
        },
        {
            "id": "explainable_ensemble_model",
            "name": "Explainable ensemble model",
            "family": "explainable AI ensemble",
            "layer": "L4",
            "detects": "rows prioritized by strongest detector evidence",
            "confidence_basis": "maximum detector-family score; not a calibrated probability",
        },
    ]
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for anomaly in anomalies:
        by_model[anomaly["model"]].append(anomaly)
    inventory = []
    for model in catalog:
        hits = by_model.get(model["name"], [])
        avg_confidence = sum(item.get("confidence", 0) for item in hits) / len(hits) if hits else 0
        inventory.append({
            **model,
            "detections": len(hits),
            "max_score": round(max((item.get("score", 0) for item in hits), default=0), 1),
            "average_confidence": round(avg_confidence, 2),
            "active": bool(hits),
        })
    return inventory


def _model_decision(summary: dict[str, Any]) -> dict[str, str]:
    if summary["critical"] or summary["high"]:
        return {
            "label": "Anomalies detected",
            "tone": "critical" if summary["critical"] else "high",
            "rationale": "The model found high-risk records that crossed robust statistical or ensemble thresholds.",
        }
    if summary["medium"]:
        return {
            "label": "Review recommended",
            "tone": "medium",
            "rationale": "The model found moderate data quality or pattern issues that should be checked.",
        }
    if summary["low"]:
        return {
            "label": "Low-risk anomalies found",
            "tone": "low",
            "rationale": "Only low-severity issues crossed a detector threshold.",
        }
    return {
        "label": "No material anomaly detected",
        "tone": "clear",
        "rationale": "No records crossed the current L1-L4 anomaly thresholds.",
    }


def _pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 3 or len(xs) != len(ys):
        return 0.0
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    x_den = math.sqrt(sum((x - x_mean) ** 2 for x in xs))
    y_den = math.sqrt(sum((y - y_mean) ** 2 for y in ys))
    if not x_den or not y_den:
        return 0.0
    return numerator / (x_den * y_den)


def _add_categorical_pair_signals(
    rows: list[dict[str, Any]],
    profiles: dict[str, dict[str, Any]],
    anomalies: list[dict[str, Any]],
    row_scores: dict[int, dict[str, Any]],
):
    categorical = [
        name for name, profile in profiles.items()
        if profile["type"] == "category" and profile.get("model_eligible", True) and 2 <= profile["unique"] <= max(12, len(rows) * 0.6)
    ][:8]
    for left_index, left in enumerate(categorical):
        for right in categorical[left_index + 1:]:
            left_counts = Counter(str(row.get(left)).strip() for row in rows if not _empty(row.get(left)))
            right_counts = Counter(str(row.get(right)).strip() for row in rows if not _empty(row.get(right)))
            pair_counts = Counter(
                (str(row.get(left)).strip(), str(row.get(right)).strip())
                for row in rows
                if not _empty(row.get(left)) and not _empty(row.get(right))
            )
            if len(pair_counts) < 3:
                continue
            paired_count = sum(pair_counts.values())
            singleton_rate = sum(1 for count in pair_counts.values() if count == 1) / paired_count if paired_count else 0
            if singleton_rate > 0.45 and len(pair_counts) > max(10, paired_count * 0.6):
                continue
            for row_index, row in enumerate(rows, start=1):
                if _empty(row.get(left)) or _empty(row.get(right)):
                    continue
                pair = (str(row.get(left)).strip(), str(row.get(right)).strip())
                if pair_counts[pair] == 1 and left_counts[pair[0]] > 1 and right_counts[pair[1]] > 1:
                    row_scores[row_index]["score"] += 18
                    row_scores[row_index]["reasons"].append(f"rare combination {left}+{right}")
                    row_scores[row_index]["contributions"].append({
                        "feature": f"{left} + {right}",
                        "impact": 18,
                        "reason": f"{pair[0]} / {pair[1]} appears once",
                    })
                    _add_anomaly(anomalies, {
                        "row": row_index,
                        "column": f"{left} + {right}",
                        "layer": "L3",
                        "type": "rare_combination",
                        "model": "Cross-column pattern model",
                        "method": "pair-frequency rarity scoring",
                        "threshold": "pair frequency = 1 while both individual values repeat",
                        "score": 54,
                        "value": f"{pair[0]} | {pair[1]}",
                        "message": f"The combination {left}={pair[0]} and {right}={pair[1]} appears only once.",
                        "explanation": {
                            "plain_language": "Each value appears elsewhere, but this exact combination is unusual.",
                            "feature_contributions": [{
                                "feature": f"{left} + {right}",
                                "impact": 54,
                                "reason": "rare cross-column pairing",
                            }],
                            "recommended_action": "Check whether one of these fields was mapped, typed, or classified incorrectly.",
                        },
                    })


def _add_numeric_relationship_signals(
    rows: list[dict[str, Any]],
    profiles: dict[str, dict[str, Any]],
    anomalies: list[dict[str, Any]],
    row_scores: dict[int, dict[str, Any]],
    ratio_pairs=(),
):
    numeric = [name for name, profile in profiles.items() if profile["type"] == "numeric" and profile.get("model_eligible", True)][:8]
    allowed_ratios = {frozenset(pair) for pair in ratio_pairs}
    for left_index, left in enumerate(numeric):
        for right in numeric[left_index + 1:]:
            paired = []
            for row_index, row in enumerate(rows, start=1):
                x = _coerce_number(row.get(left))
                y = _coerce_number(row.get(right))
                if x is not None and y is not None:
                    paired.append((row_index, x, y))
            if len(paired) < 8:
                continue
            ratios = [(row_index, y / x, x, y) for row_index, x, y in paired if x not in (0, 0.0)] if frozenset((left, right)) in allowed_ratios else []
            if len(ratios) >= 8:
                ratio_values = [item[1] for item in ratios]
                med_ratio = median(ratio_values)
                ratio_mad = median([abs(value - med_ratio) for value in ratio_values]) or 0.0
                ratio_range = max(ratio_values) - min(ratio_values)
                for row_index, ratio, x, y in ratios:
                    ratio_z = abs(0.6745 * (ratio - med_ratio) / ratio_mad) if ratio_mad else 0
                    ratio_break = ratio_mad == 0 and ratio_range > 0 and abs(ratio - med_ratio) > max(abs(med_ratio) * 0.25, 0.0001)
                    if ratio_z < 3 and not ratio_break:
                        continue
                    score = min(100, max(ratio_z * 18, 74 if ratio_break else 0))
                    row_scores[row_index]["score"] += score
                    row_scores[row_index]["reasons"].append(f"ratio break {left}/{right}")
                    row_scores[row_index]["contributions"].append({
                        "feature": f"{right} / {left}",
                        "impact": round(score, 1),
                        "reason": f"ratio {ratio:.4g} vs baseline {med_ratio:.4g}",
                    })
                    _add_anomaly(anomalies, {
                        "row": row_index,
                        "column": f"{right} / {left}",
                        "layer": "L2",
                        "type": "relationship_outlier",
                        "model": "Ratio consistency model",
                        "method": "robust ratio deviation",
                        "threshold": "ratio robust z-score >= 3, or ratio differs by 25% when baseline ratio is exact",
                        "score": score,
                        "value": round(ratio, 6),
                        "message": f"{right}/{left} ratio {ratio:.4g} is unusual; baseline ratio is about {med_ratio:.4g}.",
                        "explanation": {
                            "plain_language": f"The relationship between {left} and {right} is inconsistent on this row.",
                            "feature_contributions": [
                                {"feature": f"{right} / {left}", "impact": round(score, 1), "reason": f"ratio {ratio:.4g} vs baseline {med_ratio:.4g}"},
                                {"feature": left, "impact": 12, "reason": f"input value {x:g}"},
                                {"feature": right, "impact": 12, "reason": f"observed value {y:g}"},
                            ],
                            "recommended_action": "Check formula consistency, unit conversion, and whether one value was keyed in the wrong scale.",
                        },
                    })
            xs = [item[1] for item in paired]
            ys = [item[2] for item in paired]
            corr = _pearson(xs, ys)
            if abs(corr) < 0.8:
                continue
            x_mean = sum(xs) / len(xs)
            y_mean = sum(ys) / len(ys)
            denom = sum((x - x_mean) ** 2 for x in xs)
            if not denom:
                continue
            slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denom
            intercept = y_mean - slope * x_mean
            residuals = [abs(y - (intercept + slope * x)) for _, x, y in paired]
            med_residual = median(residuals)
            mad_residual = median([abs(value - med_residual) for value in residuals]) or 0.0
            y_range = max(ys) - min(ys)
            for (row_index, x, y), residual in zip(paired, residuals):
                robust_z = abs(0.6745 * (residual - med_residual) / mad_residual) if mad_residual else 0
                deterministic_break = mad_residual == 0 and y_range > 0 and residual > y_range * 0.2
                if robust_z < 3 and not deterministic_break:
                    continue
                score = min(100, max(robust_z * 16, 72 if deterministic_break else 0))
                row_scores[row_index]["score"] += score
                row_scores[row_index]["reasons"].append(f"relationship break {left}->{right}")
                row_scores[row_index]["contributions"].append({
                    "feature": f"{left} -> {right}",
                    "impact": round(score, 1),
                    "reason": f"residual z-score {robust_z:.2f}",
                })
                expected = intercept + slope * x
                _add_anomaly(anomalies, {
                    "row": row_index,
                    "column": f"{left} -> {right}",
                    "layer": "L2",
                    "type": "relationship_outlier",
                    "model": "Correlation residual model",
                    "method": "linear residual robust z-score",
                    "threshold": "absolute residual robust z-score >= 3, or residual > 20% of target range when baseline residual is zero",
                    "score": score,
                    "value": y,
                    "message": f"{right}={y:g} breaks its learned relationship with {left}; expected about {expected:g}.",
                    "explanation": {
                        "plain_language": f"{left} and {right} usually move together, but this row does not follow that pattern.",
                        "feature_contributions": [
                            {"feature": f"{left} -> {right}", "impact": round(score, 1), "reason": f"correlation {corr:.2f}, residual z-score {robust_z:.2f}"},
                            {"feature": right, "impact": round(min(100, residual), 1), "reason": f"actual {y:g}, expected {expected:g}"},
                        ],
                        "recommended_action": "Verify both numeric fields and check whether the row belongs to a different segment.",
                    },
                })


def _add_multivariate_distance_signals(
    rows: list[dict[str, Any]],
    profiles: dict[str, dict[str, Any]],
    anomalies: list[dict[str, Any]],
    row_scores: dict[int, dict[str, Any]],
):
    numeric = [name for name, profile in profiles.items() if profile["type"] == "numeric" and profile.get("knn_eligible", profile.get("model_eligible", True)) and profile.get("mad", 0) > 0][:10]
    if len(numeric) < 2 or len(rows) < 8:
        return

    vectors = []
    for row_index, row in enumerate(rows, start=1):
        values = []
        missing = False
        for column in numeric:
            number = _coerce_number(row.get(column))
            if number is None:
                missing = True
                break
            profile = profiles[column]
            values.append((number - profile["median"]) / (profile["mad"] or 1))
        if not missing:
            vectors.append((row_index, values))
    if len(vectors) < 8:
        return

    from scipy.spatial import cKDTree
    matrix = [vector for _, vector in vectors]
    tree = cKDTree(matrix)
    distances = []
    for start in range(0, len(matrix), 2048):
        batch, _ = tree.query(matrix[start:start + 2048], k=min(6, len(matrix)))
        for offset, neighbors in enumerate(batch):
            row_index, vector = vectors[start + offset]
            nearest = neighbors[1:]
            distances.append((row_index, float(sum(nearest) / len(nearest)), vector))

    distance_values = [item[1] for item in distances]
    threshold = _quantile(distance_values, 0.95)
    med_distance = median(distance_values)
    mad_distance = median([abs(value - med_distance) for value in distance_values]) or 0.0

    for row_index, distance, vector in distances:
        robust_z = abs(0.6745 * (distance - med_distance) / mad_distance) if mad_distance else 0
        if distance < threshold or robust_z < 2.5:
            continue
        score = min(100, max(68, robust_z * 15))
        top_features = sorted(
            [{"feature": column, "impact": round(min(100, abs(value) * 14), 1), "reason": f"scaled distance {value:.2f}"} for column, value in zip(numeric, vector)],
            key=lambda item: item["impact"],
            reverse=True,
        )[:4]
        row_scores[row_index]["score"] += score
        row_scores[row_index]["reasons"].append("multivariate distance")
        row_scores[row_index]["contributions"].extend(top_features)
        _add_anomaly(anomalies, {
            "row": row_index,
            "column": "numeric feature set",
            "layer": "L2",
            "type": "multivariate_outlier",
            "model": "K-nearest-neighbor distance model",
            "method": "robust scaled distance to nearest rows",
            "threshold": "top 5% nearest-neighbor distance and robust z-score >= 2.5",
            "score": score,
            "value": round(distance, 4),
            "message": f"Row {row_index} is far from its nearest similar rows across numeric features.",
            "explanation": {
                "plain_language": "This row is unusual when numeric fields are analyzed together as a pattern.",
                "feature_contributions": top_features,
                "recommended_action": "Inspect the full row because the combined numeric pattern is unusual, even if one field alone looks plausible.",
            },
        })


def _call_gemini(prompt: str, max_tokens: int = 450) -> dict[str, Any]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {
            "provider": "deterministic",
            "model": "local-summary",
            "status": "not_configured",
            "text": "Gemini key not found, so the report is generated from local model evidence only.",
        }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.15, "maxOutputTokens": max_tokens},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        parts = body.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts).strip()
        return {"provider": "gemini", "model": GEMINI_MODEL, "status": "generated", "text": text}
    except Exception as exc:
        return {
            "provider": "gemini",
            "model": GEMINI_MODEL,
            "status": "fallback",
            "text": f"Gemini report unavailable, using local evidence. Reason: {exc}",
        }


def _call_gemini_report(result: dict[str, Any]) -> dict[str, Any]:
    top_anomalies = [
        {
            "layer": item["layer"],
            "type": item["type"],
            "score": item["score"],
            "row": item["row"],
            "column": item["column"],
            "message": item["message"],
            "drivers": item.get("explanation", {}).get("feature_contributions", [])[:3],
        }
        for item in result["anomalies"][:8]
    ]
    prompt = (
        "You are an anomaly-detection analyst. Summarize this model output in 4 concise bullets. "
        "Do not invent anomalies. Explain why the top rows were flagged and what to check next.\n\n"
        + json.dumps({
            "decision": result["decision"],
            "summary": result["summary"],
            "layers": result["layers"],
            "top_anomalies": top_anomalies,
        }, ensure_ascii=True)
    )
    return _call_gemini(prompt)


def _local_anomaly_explanation(anomaly: dict[str, Any], analysis: dict[str, Any]) -> str:
    explanation = anomaly.get("explanation", {})
    drivers = explanation.get("feature_contributions", [])
    driver_text = "; ".join(f"{item.get('feature')}: {item.get('reason')}" for item in drivers[:4]) or anomaly["message"]
    return (
        f"Row {anomaly.get('row') or 'column-level'} was flagged by {anomaly['model']} in {anomaly['layer']}. "
        f"The score is {anomaly['score']} ({anomaly['severity']}) because {driver_text}. "
        f"Threshold used: {anomaly['threshold']}. Recommended next step: {explanation.get('recommended_action', 'Review the source record.')}"
    )


def _explain_anomaly_with_ai(analysis: dict[str, Any], anomaly: dict[str, Any]) -> dict[str, Any]:
    prompt = (
        "You are an explainable anomaly detection analyst. Explain this one anomaly in 5 short lines. "
        "Use only the supplied model evidence. Include: why flagged, strongest driver, threshold, row context, and next action.\n\n"
        + json.dumps({
            "file": analysis.get("filename"),
            "decision": analysis.get("decision"),
            "anomaly": anomaly,
            "row_snapshot": analysis.get("row_snapshots", {}).get(str(anomaly.get("row")), {}),
            "model_card": analysis.get("model_card"),
        }, ensure_ascii=True)
    )
    report = _call_gemini(prompt, max_tokens=360)
    if report["status"] != "generated":
        report["text"] = _local_anomaly_explanation(anomaly, analysis)
    return report


def _local_anomaly_chat(analysis: dict[str, Any], anomaly: dict[str, Any], message: str) -> str:
    text = message.lower()
    explanation = anomaly.get("explanation", {})
    drivers = explanation.get("feature_contributions", [])
    driver_text = ", ".join(f"{item.get('feature')} ({item.get('reason')})" for item in drivers[:4])
    if any(word in text for word in ("why", "kyun", "kyo", "reason", "waja")):
        return (
            f"This anomaly was flagged because {driver_text or anomaly['message']}. "
            f"The detector was {anomaly['model']} using {anomaly['method']}."
        )
    if any(word in text for word in ("threshold", "score", "confidence", "risk")):
        return (
            f"The score is {anomaly['score']} on a capped 0-100 risk index, with confidence {anomaly.get('confidence')}. "
            f"The threshold was: {anomaly['threshold']}."
        )
    if any(word in text for word in ("fix", "action", "karna", "next", "review")):
        return explanation.get("recommended_action", "Review the row values and verify the source record.")
    return (
        f"For row {anomaly.get('row') or 'column-level'}, the main finding is: {anomaly['message']} "
        f"Main drivers: {driver_text or 'model threshold evidence'}."
    )


def _chat_about_anomaly(analysis: dict[str, Any], anomaly: dict[str, Any], request: AnomalyChatRequest) -> dict[str, Any]:
    clean_history = [
        {"role": item.get("role", "")[:12], "content": item.get("content", "")[:1000]}
        for item in request.history[-8:]
        if item.get("role") in {"user", "assistant"} and item.get("content")
    ]
    prompt = (
        "You are an anomaly investigation assistant. Discuss only the selected anomaly and supplied evidence. "
        "Do not invent records, labels, fraud, or business facts. If evidence is insufficient, say what to verify. "
        "Answer in the user's language when possible, concise but helpful.\n\n"
        + json.dumps({
            "user_message": request.message,
            "chat_history": clean_history,
            "file": analysis.get("filename"),
            "summary": analysis.get("summary"),
            "selected_anomaly": anomaly,
            "row_snapshot": analysis.get("row_snapshots", {}).get(str(anomaly.get("row")), {}),
            "model_card": analysis.get("model_card"),
        }, ensure_ascii=True)
    )
    report = _call_gemini(prompt, max_tokens=520)
    if report["status"] != "generated":
        report["text"] = _local_anomaly_chat(analysis, anomaly, request.message)
    return report


def analyze_rows(rows: list[dict[str, Any]], *, include_all: bool = False, call_ai: bool = True, preprocessing_policy=None) -> dict[str, Any]:
    if len(rows) > MAX_ROWS or sum(len(row) for row in rows) > MAX_CELLS:
        raise HTTPException(status_code=413, detail="Dataset exceeds 100,000 rows or 2,000,000 cells. Split the file; no partial analysis was performed.")
    if not rows:
        raise HTTPException(status_code=400, detail="No rows found in this file.")

    try:
        prepared = preprocessing.prepare(rows, _profile_columns, preprocessing_policy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rows, source_rows, profiles = prepared.rows, prepared.source_rows, prepared.profiles
    columns = list(profiles)
    category_counts = {
        name: Counter(str(row.get(name)).strip() for row in rows if not _empty(row.get(name)))
        for name, profile in profiles.items()
        if profile["type"] == "category" and profile["unique_rate"] < 0.8
    }
    category_totals = {name: sum(counts.values()) for name, counts in category_counts.items()}
    anomalies: list[dict[str, Any]] = []
    row_scores: dict[int, dict[str, Any]] = defaultdict(lambda: {"score": 0.0, "reasons": [], "contributions": []})

    for issue in prepared.issues:
        _add_anomaly(anomalies, {
            "row": issue["row"], "column": issue["column"], "layer": "L1", "type": "type_mismatch",
            "model": "Schema inference rule", "method": "preprocessing validation", "threshold": "invalid numeric or calendar value",
            "score": 52, "value": issue["value"], "message": issue["reason"],
            "explanation": {"plain_language": issue["reason"],
                            "feature_contributions": [{"feature": issue["column"], "impact": 52, "reason": "Invalid source value retained as evidence"}],
                            "recommended_action": "Verify the original value before correcting it. It was not imputed."},
        })
    row_signatures = Counter(json.dumps(row, sort_keys=True, default=str) for row in source_rows)
    duplicate_signatures: set[str] = set()

    for row_index, row in enumerate(rows, start=1):
        signature = json.dumps(source_rows[row_index - 1], sort_keys=True, default=str)
        if row_signatures[signature] > 1:
            row_scores[row_index]["score"] += 28
            row_scores[row_index]["reasons"].append("duplicate row")
            row_scores[row_index]["contributions"].append({"feature": "row_signature", "impact": 28, "reason": "same row appears more than once"})
            if signature not in duplicate_signatures:
                _add_anomaly(anomalies, {
                    "row": row_index,
                    "column": "*",
                    "layer": "L1",
                    "type": "duplicate_row",
                    "model": "Data contract rule",
                    "method": "exact duplicate matching",
                    "threshold": "full row signature count > 1",
                    "score": 45,
                    "value": None,
                    "message": f"This row appears {row_signatures[signature]} times.",
                    "explanation": {
                        "plain_language": "The same complete record appears multiple times and may double count the underlying event.",
                        "feature_contributions": [{"feature": "row_signature", "impact": 45, "reason": "duplicate full-row values"}],
                        "recommended_action": "Check whether these records are expected repeats or accidental duplicates.",
                    },
                })
                duplicate_signatures.add(signature)

        for column, profile in profiles.items():
            raw = row.get(column)
            if profile.get("role") in {"identifier", "target", "context", "excluded"}:
                continue
            if _empty(raw):
                if prepared.report["profile"] == "bank_marketing" and column == "pdays" and _coerce_number(source_rows[row_index - 1].get(column)) == 999:
                    continue
                if profile["missing_rate"] >= 0.2:
                    row_scores[row_index]["score"] += 14
                    row_scores[row_index]["reasons"].append(f"missing {column}")
                    row_scores[row_index]["contributions"].append({"feature": column, "impact": 14, "reason": "missing in a high-missing column"})
                continue

            if not profile.get("model_eligible", True):
                continue

            if profile["type"] == "numeric":
                number = _coerce_number(raw)
                if number is None:
                    _add_anomaly(anomalies, {
                        "row": row_index,
                        "column": column,
                        "layer": "L1",
                        "type": "type_mismatch",
                        "model": "Schema inference rule",
                        "method": "numeric type consistency",
                        "threshold": "column inferred numeric but value is not numeric",
                        "score": 52,
                        "value": raw,
                        "message": f"'{raw}' is not numeric while most values in {column} are numeric.",
                        "explanation": {
                            "plain_language": "This value does not match the inferred data type of the column.",
                            "feature_contributions": [{"feature": column, "impact": 52, "reason": "non-numeric value in numeric column"}],
                            "recommended_action": "Fix the value or split mixed fields into separate columns.",
                        },
                    })
                    continue
                signal, contributions = _numeric_signal(number, profile)
                if signal >= 40:
                    row_scores[row_index]["score"] += signal
                    row_scores[row_index]["reasons"].append(f"outlier in {column}")
                    row_scores[row_index]["contributions"].extend(contributions)
                    _add_anomaly(anomalies, {
                        "row": row_index,
                        "column": column,
                        "layer": "L2",
                        "type": "numeric_outlier",
                        "model": "Robust outlier model",
                        "method": "MAD robust z-score + standard z-score + IQR fence",
                        "threshold": "model score >= 40",
                        "score": signal,
                        "value": number,
                        "message": f"Value {number:g} is unusual for {column}.",
                        "explanation": {
                            "plain_language": f"{column} is far from the column's normal range in this file.",
                            "feature_contributions": contributions,
                            "recommended_action": "Validate the source record, unit, decimal placement, and business context for this row.",
                        },
                    })
            elif profile["type"] == "category":
                all_counts = category_counts.get(column)
                if not all_counts:
                    continue
                count = all_counts[str(raw).strip()]
                present = category_totals[column]
                rarity_score = min(58, 34 + (100 / max(1, count)))
                if present >= 10 and count == 1 and profile["unique_rate"] < 0.8:
                    row_scores[row_index]["score"] += 22
                    row_scores[row_index]["reasons"].append(f"rare category in {column}")
                    row_scores[row_index]["contributions"].append({"feature": column, "impact": 22, "reason": f"'{raw}' appears once"})
                    _add_anomaly(anomalies, {
                        "row": row_index,
                        "column": column,
                        "layer": "L3",
                        "type": "rare_category",
                        "model": "Frequency rarity model",
                        "method": "category frequency scoring",
                        "threshold": "value frequency = 1 and column unique-rate < 80%",
                        "score": max(42, rarity_score),
                        "value": raw,
                        "message": f"'{raw}' appears only once in {column}.",
                        "explanation": {
                            "plain_language": "This label is rare compared with the rest of the same column.",
                            "feature_contributions": [{"feature": column, "impact": round(rarity_score, 1), "reason": f"frequency {count} of {present}"}],
                            "recommended_action": "Check spelling, mapping, and whether this category is valid.",
                        },
                    })

    _add_categorical_pair_signals(rows, profiles, anomalies, row_scores)
    _add_numeric_relationship_signals(rows, profiles, anomalies, row_scores, prepared.policy.ratio_pairs)
    _add_multivariate_distance_signals(rows, profiles, anomalies, row_scores)

    for column, profile in profiles.items():
        if profile["missing_rate"] >= 0.2:
            score = min(100, profile["missing_rate"] * 120)
            _add_anomaly(anomalies, {
                "row": None,
                "column": column,
                "layer": "L1",
                "type": "missing_values",
                "model": "Data completeness rule",
                "method": "missing-rate threshold",
                "threshold": "missing rate >= 20%",
                "score": score,
                "value": None,
                "message": f"{profile['missing']} of {len(rows)} rows are missing {column}.",
                "explanation": {
                    "plain_language": "A large share of this column is blank, so downstream analysis may be unreliable.",
                    "feature_contributions": [{"feature": column, "impact": round(score, 1), "reason": f"{profile['missing_rate'] * 100:.1f}% missing"}],
                    "recommended_action": "Review extraction mapping or source completeness for this field.",
                },
            })

    # Repeated tests of related features must not accumulate unlimited risk.
    # Keep the strongest evidence per detector family and use the strongest
    # family as the review priority. This is not a calibrated probability.
    family_scores = defaultdict(dict)
    for finding in anomalies:
        if finding.get("row") is not None:
            scores = family_scores[finding["row"]]
            family = finding["model"]
            scores[family] = max(scores.get(family, 0), finding["score"])
    for row_index, scores in family_scores.items():
        row_scores[row_index]["score"] = max(scores.values(), default=0)

    row_findings = []
    for row_index, detail in row_scores.items():
        score = min(100, detail["score"])
        if score >= 35:
            top = sorted(detail["contributions"], key=lambda item: item["impact"], reverse=True)[:5]
            row_findings.append({
                "row": row_index,
                "score": round(score, 1),
                "severity": _severity(score),
                "reasons": detail["reasons"][:6],
                "feature_contributions": top,
            })

    for row_finding in row_findings:
        if row_finding["score"] >= 55:
            _add_anomaly(anomalies, {
                "row": row_finding["row"],
                "column": "*",
                "layer": "L4",
                "type": "row_risk_explanation",
                "model": "Explainable ensemble model",
                "method": "maximum detector-family score; repeated signals do not add risk",
                "threshold": "row risk score >= 55",
                "score": row_finding["score"],
                "value": None,
                "message": f"Row {row_finding['row']} is prioritized for analyst review based on detector evidence.",
                "explanation": {
                    "plain_language": "Priority is the strongest detector-family score, not a probability of error. Related signals are not added together.",
                    "feature_contributions": row_finding["feature_contributions"],
                    "recommended_action": "Inspect the original evidence; priority does not confirm an error.",
                },
            })

    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    layer_rank = {"L4": 0, "L2": 1, "L1": 2, "L3": 3}
    anomalies.sort(key=lambda item: (severity_rank[item["severity"]], layer_rank[item["layer"]], -(item["score"] or 0), item["row"] or 0))

    layer_counts = {layer: sum(1 for item in anomalies if item["layer"] == layer) for layer in ("L1", "L2", "L3", "L4")}
    severity_counts = {severity: sum(1 for item in anomalies if item["severity"] == severity) for severity in ("critical", "high", "medium", "low")}
    max_score = max([item["score"] for item in anomalies], default=0)
    top_drivers = Counter(item["type"] for item in anomalies).most_common(5)
    summary = {
        "total_anomalies": len(anomalies),
        "shown_anomalies": min(len(anomalies), 300),
        "critical": severity_counts["critical"],
        "high": severity_counts["high"],
        "medium": severity_counts["medium"],
        "low": severity_counts["low"],
        "max_risk_score": round(max_score, 1),
        "data_quality_score": prepared.report["cell_quality_score"],
    }
    distributions = []
    for column, profile in profiles.items():
        if profile["type"] == "numeric":
            numbers = [_coerce_number(row.get(column)) for row in rows]
            numbers = [value for value in numbers if value is not None]
            distributions.append({
                "column": column,
                "histogram": _histogram(numbers),
                "median": profile.get("median"),
                "mean": profile.get("mean"),
                "min": profile.get("min"),
                "max": profile.get("max"),
            })

    sorted_row_findings = sorted(row_findings, key=lambda item: item["score"], reverse=True)
    score_points, driver_breakdown, row_snapshots = _chart_evidence(source_rows, columns, anomalies, sorted_row_findings)
    model_inventory = _model_inventory(anomalies)
    for anomaly in anomalies:
        if anomaly.get("row"):
            anomaly["row_values"] = row_snapshots.get(str(anomaly["row"]), {}).get("values", {})
            anomaly["prepared_row_values"] = _compact_row(rows[anomaly["row"] - 1], columns)
            if anomaly["column"] in profiles:
                anomaly["original_value"] = source_rows[anomaly["row"] - 1].get(anomaly["column"])
                anomaly["prepared_value"] = rows[anomaly["row"] - 1].get(anomaly["column"])

    if not include_all:
        visible_rows = {str(item["row"]) for item in anomalies[:300] + sorted_row_findings[:50] if item.get("row")}
        row_snapshots = {key: value for key, value in row_snapshots.items() if key in visible_rows}

    result = {
        "row_count": len(rows),
        "column_count": len(columns),
        "columns": list(profiles.values()),
        "preview_rows": _preview_rows(source_rows, columns),
        "prepared_preview_rows": _preview_rows(rows, columns),
        "preprocessing": prepared.report,
        "distributions": distributions[:8],
        "numeric_plots": _numeric_plots(rows, profiles),
        "anomalies": anomalies if include_all else anomalies[:300],
        "row_findings": sorted_row_findings[:50],
        "score_points": score_points,
        "driver_breakdown": driver_breakdown,
        "row_snapshots": row_snapshots,
        "model_inventory": model_inventory,
        "risk_distribution": _risk_distribution(row_findings, len(rows)),
        "severity_distribution": _severity_distribution(summary),
        "layers": [
            {"id": "L1", "name": "Data Quality", "model": "schema and completeness rules", "count": layer_counts["L1"], "description": "Finds missing values, duplicates, and type mismatches."},
            {"id": "L2", "name": "Statistical Model", "model": "robust outlier ensemble", "count": layer_counts["L2"], "description": "Scores numeric values using robust z-score, standard z-score, and IQR fences."},
            {"id": "L3", "name": "Pattern Model", "model": "frequency and rarity scoring", "count": layer_counts["L3"], "description": "Finds unusual labels and low-frequency categorical values."},
            {"id": "L4", "name": "Explainable AI", "model": "strongest detector evidence", "count": layer_counts["L4"], "description": "Combines signals into row-level risk and explains feature contributions."},
        ],
        "summary": summary,
        "decision": _model_decision(summary),
        "analyst_summary": [
            f"{summary['total_anomalies']} detector findings across {len(rows)} rows; a row can have multiple findings.",
            f"Highest row/model risk score is {summary['max_risk_score']}.",
            f"Most common drivers: {', '.join(name.replace('_', ' ') for name, _ in top_drivers) or 'none'}.",
            "Review L4 rows first based on their strongest detector evidence." if layer_counts["L4"] else "No L4 ensemble row crossed the escalation threshold; review the highest L2/L3 items first.",
        ],
        "model_card": {
            "name": "Generic Explainable Anomaly Ensemble",
            "version": "1.0-local",
            "training": "Unsupervised per-file baseline; no external training data required.",
            "model_count": len(model_inventory),
            "active_model_count": sum(1 for item in model_inventory if item["active"]),
            "features": ["numeric distance", "missing rate", "duplicate signature", "type consistency", "category rarity", "pair rarity", "correlation residual"],
            "thresholds": [
                "L1 flags duplicate rows, type mismatches, and columns with >= 20% missing values.",
                "L2 flags numeric outliers at score >= 40; ratios require configured pairs; KNN checks the top 5% of distances.",
                "L3 flags rare categories and rare categorical pairings when frequency evidence is strong.",
                "L4 escalates a row when combined lower-layer risk reaches >= 55.",
            ],
            "decision_policy": "Critical starts at score 85, high at 65, medium at 40, and low below 40.",
            "explainability": "Each anomaly includes layer, model, score, confidence, threshold, and feature contributions.",
            "limitations": "Without business labels or historical data, this agent identifies statistical unusualness, not guaranteed fraud or error. Confidence is a heuristic score, not a calibrated probability.",
        },
    }
    if include_all:
        result["_prepared_rows"] = rows
    if not include_all:
        numeric_columns = [name for name, profile in profiles.items() if profile["type"] == "numeric"][:8]
        flagged_rows = {item["row"] for item in anomalies if item.get("row")}
        result["statistical_graphs"] = _statistical_graphs([
            {"row": index, "values": {name: _coerce_number(row.get(name)) for name in numeric_columns},
             "flagged": index in flagged_rows}
            for index, row in enumerate(rows, 1)
        ], numeric_columns)
    result["ai_report"] = _call_gemini_report(result) if call_ai else {
        "status": "local", "provider": "local", "model": "Batch analysis",
        "text": "Every record is checked against its batch baseline. Cross-batch patterns are not evaluated.",
    }
    return result


@router.post("/anomaly/analyze-file")
def analyze_file(file: UploadFile = File(...)):
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if not size:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 64 MiB.")
    name = file.filename or "uploaded-data"
    stream = io.TextIOWrapper(file.file, encoding="utf-8-sig")
    try:
        if name.lower().endswith(".json"):
            rows = _json_rows(json.load(stream))
            file_type = "json"
        elif name.lower().endswith((".csv", ".jsonl", ".ndjson")):
            file_type = "csv" if name.lower().endswith(".csv") else "jsonl"
            source = _csv_reader(stream) if file_type == "csv" else (_flatten(json.loads(line)) for line in stream if line.strip())
            rows = []
            cells = 0
            for row in source:
                cells += len(row)
                if len(rows) >= MAX_ROWS or cells > MAX_CELLS:
                    raise HTTPException(status_code=413, detail="Dataset exceeds 100,000 rows or 2,000,000 cells. Split the file; no partial analysis was performed.")
                rows.append(dict(row))
        else:
            raise HTTPException(status_code=400, detail="Use CSV, JSON, or JSONL.")
    except (ValueError, UnicodeError, csv.Error) as exc:
        raise HTTPException(status_code=400, detail="Invalid file encoding or data. Use UTF-8 CSV, JSON, or JSONL.") from exc
    finally:
        stream.detach()

    result = analyze_rows(rows)
    analysis_id = str(uuid4())
    result.update({
        "analysis_id": analysis_id,
        "filename": name,
        "file_type": file_type,
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    })
    ANALYSES[analysis_id] = result
    _save_analysis(result)
    return result


@router.get("/anomaly/analyses")
def list_analyses():
    memory_items = {_history_item(item)["analysis_id"]: _history_item(item) for item in ANALYSES.values()}
    for item in _list_saved_analyses():
        memory_items[item["analysis_id"]] = item
    return sorted(memory_items.values(), key=lambda item: item.get("created_at") or "", reverse=True)[:25]


@router.get("/anomaly/analyses/{analysis_id}")
def get_analysis(analysis_id: str):
    result = _load_analysis(analysis_id)
    if not result:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return result


@router.post("/anomaly/analyses/{analysis_id}/anomalies/{anomaly_id}/explain")
def explain_anomaly(analysis_id: str, anomaly_id: str):
    result = _load_analysis(analysis_id)
    if not result:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    anomaly = next((item for item in result.get("anomalies", []) if item.get("id") == anomaly_id), None)
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found.")
    explanation = _explain_anomaly_with_ai(result, anomaly)
    anomaly["ai_explanation"] = explanation
    ANALYSES[analysis_id] = result
    _save_analysis(result)
    return explanation


@router.post("/anomaly/analyses/{analysis_id}/anomalies/{anomaly_id}/chat")
def chat_about_anomaly(analysis_id: str, anomaly_id: str, request: AnomalyChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message is required.")
    result = _load_analysis(analysis_id)
    if not result:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    anomaly = next((item for item in result.get("anomalies", []) if item.get("id") == anomaly_id), None)
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found.")
    return _chat_about_anomaly(result, anomaly, request)
