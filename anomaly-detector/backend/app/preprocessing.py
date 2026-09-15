"""Auditable, non-destructive preparation before anomaly detectors run.

No rows are dropped, no extreme values are clipped, and missing values are not
invented. Existing detectors skip unavailable numeric inputs. Original values
remain available for quality findings and raw/model row comparisons.
"""

import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

MISSING_TOKENS = frozenset({"unknown", "null", "none", "nan", "n/a"})
NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
GROUPED = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?$")
BANK_COLUMNS = frozenset({"age", "job", "marital", "education", "default", "housing", "loan",
                          "contact", "month", "day_of_week", "duration", "campaign", "pdays",
                          "previous", "poutcome", "emp.var.rate", "cons.price.idx", "cons.conf.idx",
                          "euribor3m", "nr.employed", "y"})
BANK_CONTEXT = frozenset({"emp.var.rate", "cons.price.idx", "cons.conf.idx", "euribor3m", "nr.employed"})


def parse_number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            number = float(value)
        except OverflowError:
            return None
    elif isinstance(value, str):
        text = value.strip()
        for token in ("PKR", "USD", "EUR", "$", "€"):
            if text.upper().startswith(token):
                text = text[len(token):].strip()
                break
        if text.endswith("%"):
            text = text[:-1].strip()
        if "," in text:
            if not GROUPED.fullmatch(text):
                return None
            text = text.replace(",", "")
        if not NUMBER.fullmatch(text):
            return None
        number = float(text)
    else:
        return None
    return number if math.isfinite(number) else None


@dataclass(frozen=True)
class Policy:
    profile: str = "auto"
    excluded_columns: tuple = ()
    target_columns: tuple = ("target", "label", "is_anomaly", "is_fraud")
    ratio_pairs: tuple = ()

    @classmethod
    def from_environment(cls):
        profile = os.getenv("ANOMALY_PREPROCESSING_PROFILE", "auto")
        if profile not in {"auto", "generic", "bank_marketing"}:
            raise ValueError("ANOMALY_PREPROCESSING_PROFILE must be auto, generic or bank_marketing.")
        pairs = json.loads(os.getenv("ANOMALY_RATIO_PAIRS", "[]"))
        if not isinstance(pairs, list) or len(pairs) > 28 or any(
            not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(c, str) for c in pair) or pair[0] == pair[1]
            for pair in pairs
        ):
            raise ValueError("ANOMALY_RATIO_PAIRS must contain at most 28 pairs of different column names.")
        return cls(profile=profile,
                   excluded_columns=tuple(c.strip() for c in os.getenv("ANOMALY_EXCLUDED_COLUMNS", "").split(",") if c.strip()),
                   target_columns=tuple(c.strip() for c in os.getenv("ANOMALY_TARGET_COLUMNS", "target,label,is_anomaly,is_fraud").split(",") if c.strip()),
                   ratio_pairs=tuple(tuple(pair) for pair in pairs))


@dataclass
class PreparedData:
    source_rows: list
    rows: list
    profiles: dict
    issues: list
    report: dict
    policy: Policy


def prepare(rows, profile_columns, policy=None):
    policy = policy or Policy.from_environment()
    raw_names = sorted({name for row in rows for name in row}, key=str)
    if any(not isinstance(name, str) or not name.strip().lstrip("\ufeff") for name in raw_names):
        raise ValueError("Every column must have a non-empty text header.")
    mapping = {name: name.strip().lstrip("\ufeff") for name in raw_names}
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("Column names collide after whitespace normalization. Rename them before upload.")
    names = sorted(mapping.values())
    bank = policy.profile == "bank_marketing" or (policy.profile == "auto" and BANK_COLUMNS.issubset(names))
    if bank and not BANK_COLUMNS.issubset(names):
        raise ValueError("Bank Marketing profile requires the documented bank-additional columns.")
    source = [{mapping[name]: value for name, value in row.items()} for row in rows]
    clean = []
    counts = {name: Counter() for name in names}
    units = {name: set() for name in names}
    numeric_styles = {name: set() for name in names}
    issues, examples = [], []
    example_counts = Counter()

    def change(index, name, original, prepared, reason):
        counts[name][reason] += 1
        if len(examples) < 40 and example_counts[reason] < 5:
            examples.append({"row": index, "column": name, "original": original, "prepared": prepared, "reason": reason})
            example_counts[reason] += 1

    for index, row in enumerate(source, 1):
        output = {}
        for name in names:
            original = row.get(name)
            value = original
            if isinstance(value, str):
                value = value.strip()
                if value != original:
                    change(index, name, original, value, "trimmed")
            if value is None or value == "":
                value = None
                change(index, name, original, None, "blank")
            elif isinstance(value, str) and value.casefold() in MISSING_TOKENS:
                value = None
                change(index, name, original, None, "missing_token")
            elif (isinstance(value, float) and not math.isfinite(value)) or (
                isinstance(value, str) and value.casefold() in {"inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}
            ):
                value = None
                source[index - 1][name] = str(original)
                change(index, name, str(original), None, "invalid")
                issues.append({"row": index, "column": name, "value": str(original), "reason": "Non-finite number is not a valid model input."})
            elif isinstance(value, str) and re.fullmatch(r"\d{4}[-/]\d{2}[-/]\d{2}", value):
                try:
                    date = datetime.strptime(value.replace("/", "-"), "%Y-%m-%d").date().isoformat()
                    if date != value:
                        change(index, name, original, date, "date_normalized")
                    value = date
                except ValueError:
                    value = None
                    change(index, name, original, None, "invalid")
                    issues.append({"row": index, "column": name, "value": original, "reason": "Invalid year-first calendar date."})
            if value is not None and parse_number(value) is not None:
                text = str(value).upper()
                for token, unit in (("PKR", "PKR"), ("USD", "USD"), ("EUR", "EUR"), ("$", "USD"), ("€", "EUR")):
                    if text.startswith(token):
                        units[name].add(unit)
                        break
                numeric_styles[name].add("percent" if text.endswith("%") else "plain")
            output[name] = value
        clean.append(output)

    _, inferred = profile_columns(clean)
    roles, reasons = {}, {}
    for name, profile in inferred.items():
        token = name.lower().replace("-", "_").replace(" ", "_").split(".")[-1]
        identifier = token in {"id", "index", "serial", "serial_no", "s_no"} or token.endswith("_id")
        role = profile["type"]
        reason = "Eligible for detectors that support this data type."
        if name in policy.excluded_columns:
            role, reason = "excluded", "Excluded by deployment policy."
        elif name in policy.target_columns or (bank and name == "y"):
            role, reason = "target", "Outcome/target is excluded from anomaly features."
        elif identifier:
            role, reason = "identifier", "Identifiers retain their original text and are excluded from model features."
        elif token in {"date", "datetime", "timestamp", "time", "candel_time", "candle_time", "am/pm"} or profile["type"] == "date":
            role, reason = "context", "Temporal context is retained for review; timestamp rarity is not evidence of an anomaly. Ambiguous date formats require explicit interpretation."
        elif bank and name in BANK_CONTEXT:
            role, reason = "context", "Population/time context; excluded from individual-record anomaly models."
        elif len(units[name]) > 1 or len(numeric_styles[name]) > 1:
            role, reason = "excluded", "Mixed currencies or percent/plain representations need an explicit unit mapping."
        roles[name], reasons[name] = role, reason

    for index, row in enumerate(clean, 1):
        for name in names:
            value = row[name]
            if bank and name == "pdays" and parse_number(value) == 999:
                row[name] = None
                change(index, name, source[index - 1].get(name), None, "not_applicable")
            elif value is not None and inferred[name]["type"] == "numeric" and roles[name] not in {"identifier", "target", "excluded"}:
                number = parse_number(value)
                if number is None:
                    row[name] = None
                    change(index, name, source[index - 1].get(name), None, "invalid")
                    issues.append({"row": index, "column": name, "value": source[index - 1].get(name),
                                   "reason": "Value does not match the inferred numeric type; excluded from numeric inputs."})
                else:
                    row[name] = number
                    if isinstance(value, str):
                        change(index, name, source[index - 1].get(name), number, "numeric_parsed")

    _, profiles = profile_columns(clean)
    for name, profile in profiles.items():
        count = counts[name]
        role = roles[name]
        if role == "identifier":
            profile["type"] = "identifier"
        elif role == "target":
            profile["type"] = "target"
        elif role == "excluded":
            profile["type"] = "excluded"
        elif inferred[name]["type"] == "numeric" and profile["type"] != "numeric":
            profile["type"] = "numeric"
        usable = len(rows) - count["not_applicable"]
        missing = count["blank"] + count["missing_token"]
        eligible = role in {"numeric", "category"} and profile["unique"] > 1
        profile.update(missing=missing, missing_rate=round(missing / usable, 4) if usable else 0,
                       invalid=count["invalid"], not_applicable=count["not_applicable"],
                       role=role, model_eligible=eligible)
        observed = len(rows) - missing - count["invalid"] - count["not_applicable"]
        profile["knn_eligible"] = eligible and profile["type"] == "numeric" and observed / len(rows) >= .8
        if role in {"numeric", "category"} and not eligible:
            reasons[name] = "Constant or entirely unavailable column; retained for quality checks only."

    signatures = Counter(json.dumps(row, sort_keys=True, default=str) for row in source)
    totals = Counter()
    for count in counts.values():
        totals.update(count)
    total_cells = len(rows) * len(names)
    unavailable = totals["blank"] + totals["missing_token"] + totals["invalid"]
    eligible_cells = total_cells - totals["not_applicable"]
    quality = round(100 * (1 - unavailable / eligible_cells), 2) if eligible_cells else None
    report = {
        "version": "1.0", "status": "completed", "profile": "bank_marketing" if bank else "generic",
        "scope": "file", "input_rows": len(rows), "output_rows": len(clean), "dropped_rows": 0, "imputed_cells": 0,
        "total_cells": total_cells, "eligible_cells": eligible_cells, "unavailable_cells": unavailable,
        "cell_quality_score": quality, "counts": dict(totals),
        "duplicate_extra_rows": sum(count - 1 for count in signatures.values()),
        "duplicate_groups": sum(count > 1 for count in signatures.values()),
        "header_mapping": mapping, "examples": examples,
        "columns": [{"name": name, "type": profiles[name]["type"], "role": profiles[name]["role"],
                     "knn_eligible": profiles[name]["knn_eligible"],
                     "model_eligible": profiles[name]["model_eligible"], "reason": reasons[name],
                     "counts": dict(counts[name])} for name in names],
        "ratio_pairs": [list(pair) for pair in policy.ratio_pairs],
        "steps": ["Schema validation", "Whitespace and missing-value normalization", "Numeric/date validation",
                  "Column roles and domain rules", "Model eligibility", "Anomaly detection"],
        "policy": "No rows removed, no outliers clipped, no missing values imputed. Unavailable numeric inputs are skipped. Categories remain labels. KNN uses median/MAD scaling and features with at least 80% observed values; it skips rows incomplete on those features.",
        "quality_definition": "Percentage of known, valid cells; documented not-applicable values are excluded. Duplicate counts are reported separately. This is not an anomaly-confidence score.",
        "evidence_scope": "Up to 40 transformation examples plus original/prepared values for retained findings; bulk findings retain their own row evidence.",
    }
    if bank:
        report["domain_notes"] = ["pdays=999 means not previously contacted; represented as not applicable, not an outlier or quality defect.",
                                  "The y target and five macroeconomic context columns are excluded from individual-record models."]
        report["dictionary_source"] = "https://archive.ics.uci.edu/static/public/222/bank+marketing.zip"
    return PreparedData(source, clean, profiles, issues, report, policy)
