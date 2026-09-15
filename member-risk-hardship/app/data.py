import hashlib
import io
import json
import re
import zipfile
import numpy as np
import pandas as pd
from app.store import identifier

ALIASES = {
 'member_id': ['cust_id', 'cust_no', 'customer_id', 'member_id', 'account_id'],
 'loan_amount': ['loan_amount', 'loan_value', 'loan_amt', 'original_loan_amount'],
 'income': ['income', 'salary', 'declared_income'],
 'late_payments': ['late_payments', 'late_cnt', 'late_count', 'late_payment_count', 'late_payments_6m'],
 'missed_payments': ['missed_payments', 'missed_inst', 'unpaid_installments', 'missed_payment_count', 'missed_payments_6m'],
 'days_past_due': ['days_past_due', 'dpd'],
 'target_arrears': ['arrears_flag', 'target_arrears', 'default_flag', 'target'],
 'prediction_date': ['prediction_date', 'snapshot_date', 'as_of_date'],
 'payment_month': ['payment_month', 'month'],
}
NUMERIC = {'loan_amount', 'income', 'late_payments', 'missed_payments', 'days_past_due',
 'outstanding_balance', 'installment_amount', 'loan_term', 'interest_rate', 'partial_payment_count',
 'payment_ratio', 'days_since_last_payment', 'dpd_trend', 'balance_trend', 'payment_ratio_trend',
 'late_payment_trend', 'debt_to_income_ratio', 'installment_to_income_ratio', 'amount_due', 'amount_paid', 'balance'}
ALLOW = NUMERIC | {'loan_type', 'repayment_frequency'}
PROTECTED = {'race', 'ethnicity', 'religion', 'disability', 'gender', 'sex', 'age', 'nationality', 'political_affiliation', 'marital_status'}
PROXY = {'postcode', 'zip', 'zipcode', 'neighborhood', 'language', 'surname', 'name', 'address', 'email', 'phone'}
LEAKAGE = re.compile(r'future|final_default|write.?off|recovery|collection_outcome|after_default|after_prediction', re.I)

def normalize(name):
    return re.sub(r'[^a-z0-9]+', '_', str(name).lower()).strip('_')

def flags(column):
    n = normalize(column)
    tokens = set(n.split('_'))
    if n in PROTECTED or tokens & PROTECTED or 'political' in tokens:
        return 'protected'
    if n in PROXY or tokens & PROXY:
        return 'review'
    if LEAKAGE.search(n):
        return 'leakage'
    return None

def propose_mapping(df):
    inverse = {alias: key for key, aliases in ALIASES.items() for alias in aliases}
    return {c: inverse.get(normalize(c), normalize(c)) for c in df.columns}

def validate_mapping(df, mapping):
    if set(mapping) != set(df.columns):
        raise ValueError('Mapping must include every source column exactly once')
    if len(set(mapping.values())) != len(mapping):
        raise ValueError('Canonical mapping contains duplicate destinations')
    for source, target in mapping.items():
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,80}', target):
            raise ValueError('Invalid canonical field name')
        if flags(source) and target in ALLOW:
            raise ValueError('Sensitive, proxy or leakage columns cannot be renamed into approved features')
    return mapping

def profile(df):
    mapping = propose_mapping(df)
    target = next((c for c, v in mapping.items() if v == 'target_arrears'), None)
    counts = df[target].value_counts().to_dict() if target else {}
    labelled = df[target].dropna() if target else pd.Series(dtype=float)
    state = 'NO_LABELS' if len(labelled) == 0 else ('GOOD_DATA' if len(df) >= 200 and len(counts) == 2 and min(counts.values()) >= 30 else 'PARTIAL_DATA')
    columns = []
    for c in df:
        s = df[c]
        item = {'name': c, 'canonical_proposal': mapping[c], 'dtype': str(s.dtype), 'missing_pct': round(float(s.isna().mean() * 100), 2), 'unique_count': int(s.nunique()), 'flag': flags(c)}
        if pd.api.types.is_numeric_dtype(s) and s.notna().any():
            finite = s[np.isfinite(s)]
            if len(finite):
                q1, q3 = finite.quantile([.25, .75])
                item['numeric_summary'] = {'min': float(finite.min()), 'max': float(finite.max()), 'median': float(finite.median()), 'outlier_count': int(((finite < q1-1.5*(q3-q1)) | (finite > q3+1.5*(q3-q1))).sum())}
        if mapping[c] in ('prediction_date', 'payment_month'):
            dates = pd.to_datetime(s, errors='coerce', utc=True)
            item['date_coverage'] = {'min': str(dates.min()), 'max': str(dates.max()), 'invalid': int(dates.isna().sum())}
        columns.append(item)
    member = next((c for c,v in mapping.items() if v == 'member_id'), None)
    lengths = df.groupby(member).size() if member else pd.Series([1])
    return {'row_count': len(df), 'column_count': len(df.columns), 'duplicate_count': int(df.duplicated().sum()), 'quality_state': state,
      'columns': columns, 'target_candidates': [target] if target else [], 'target_distribution': {str(k): int(v) for k,v in counts.items()},
      'class_imbalance_ratio': float(max(counts.values()) / min(counts.values())) if counts else None,
      'sequence_length_median': float(lengths.median()), 'has_sequence_data': bool(member and 'payment_month' in mapping.values() and lengths.median() >= 6)}

def parse_upload(content: bytes, filename: str):
    suffix = filename.lower().rsplit('.', 1)[-1]
    if suffix == 'csv':
        df = pd.read_csv(io.BytesIO(content))
    elif suffix == 'xlsx':
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if sum(x.file_size for x in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError('Expanded workbook exceeds 100 MB')
        df = pd.read_excel(io.BytesIO(content), engine='openpyxl')
    elif suffix == 'json':
        records = json.loads(content)
        if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
            raise ValueError('JSON must contain an array of records')
        df = pd.DataFrame(records)
    else:
        raise ValueError('Only CSV, XLSX and JSON files are accepted')
    if not 1 <= len(df) <= 200000 or not 1 <= len(df.columns) <= 200:
        raise ValueError('Dataset must contain 1–200000 rows and 1–200 columns')
    df.columns = [str(c) for c in df.columns]
    if len(set(df.columns)) != len(df.columns):
        raise ValueError('Duplicate column names')
    if any(df[c].map(lambda x: isinstance(x, (dict, list))).any() for c in df):
        raise ValueError('Nested records are not accepted')
    return df

def upload(store, tid, content, filename):
    df = parse_upload(content, filename)
    did = identifier('dataset')
    df.to_json(store.path(tid, 'datasets', did + '.json'), orient='records', date_format='iso')
    body = {'dataset_id': did, 'sha256': hashlib.sha256(content).hexdigest(), 'profile': profile(df), 'mapping': propose_mapping(df)}
    store.put(tid, 'dataset', did, body)
    store.audit(tid, 'dataset.uploaded', {'dataset_id': did, 'rows': len(df)})
    return body

def load_dataset(store, tid, did):
    meta = store.get(tid, 'dataset', did)
    return pd.read_json(store.path(tid, 'datasets', did + '.json')), meta

def canonical_frame(df, mapping):
    validate_mapping(df, mapping)
    return df.rename(columns=mapping).drop_duplicates().reset_index(drop=True)

def approved_features(df, mapping, target):
    leaks = [c for c in df if flags(c) == 'leakage' and c != target]
    leaks += [s for s,t in mapping.items() if flags(s) == 'leakage' and t != target]
    if leaks:
        raise ValueError('Critical leakage columns must be removed from the uploaded dataset: ' + ', '.join(leaks))
    features = [c for c in df if c in ALLOW and c != target]
    if not features:
        raise ValueError('No approved predictive features found')
    for c in features:
        if c in NUMERIC:
            numeric = pd.to_numeric(df[c], errors='coerce')
            if (df[c].notna() & numeric.isna()).any() or np.isinf(numeric).any():
                raise ValueError(f'Invalid numeric values in {c}')
            if c not in {'dpd_trend', 'balance_trend', 'payment_ratio_trend', 'late_payment_trend'} and (numeric < 0).any():
                raise ValueError(f'Negative values in {c}')
            df[c] = numeric
        else:
            if df[c].nunique() > 100:
                raise ValueError(f'Categorical cardinality too high: {c}')
            df[c] = df[c].fillna('missing').astype(str)
    return features
