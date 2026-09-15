import hashlib
from functools import lru_cache
import joblib
import numpy as np
import pandas as pd
from app.data import NUMERIC, ALIASES
from app.models import Ensemble, CalibratedRisk
from app.hardship import detect_hardship,evaluate_policy

@lru_cache(maxsize=32)
def cached_load(path, sha256):
    from pathlib import Path
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != sha256:
        raise ValueError('Model artifact integrity check failed')
    # Only artifacts produced by this service may be loaded. Uploads cannot select this path.
    return joblib.load(path)

def load_model(store,tid,version=None):
    models = store.list(tid,'model')
    meta = next((m for m in models if (m['model_version']==version if version else m['status']=='production')),None)
    if meta is None: raise ValueError('No validated production model exists; risk probability unavailable')
    artifact = cached_load(str(store.path(tid,'models',meta['model_version']+'.joblib')),meta['artifact_sha256'])
    return meta,artifact

def map_record(record,artifact):
    inverse = {alias:key for key,aliases in ALIASES.items() for alias in aliases}
    mapped = {}
    for key,value in record.items():
        dest = artifact['mapping'].get(key,inverse.get(key,key))
        if dest in mapped: raise ValueError('Conflicting source and canonical fields')
        mapped[dest]=value
    missing = set(artifact['features'])-set(mapped)
    if missing: raise ValueError('Missing required features: '+', '.join(sorted(missing)))
    row = {f:mapped[f] for f in artifact['features']}
    for f,value in row.items():
        if f in NUMERIC:
            if value is None: row[f]=np.nan
            else:
                try: row[f]=float(value)
                except (TypeError,ValueError): raise ValueError(f'Invalid numeric input: {f}')
                if not np.isfinite(row[f]) or ('trend' not in f and row[f]<0): raise ValueError(f'Invalid numeric range: {f}')
        else: row[f]='missing' if value is None else str(value)
    return row

def transform(request,artifact):
    if artifact['sequence']:
        history = request.history
        if len(history)<artifact['steps']: raise ValueError('Provide at least six dated historical records for this sequence model')
        dates = pd.to_datetime([r.get('payment_month') for r in history],errors='coerce',utc=True)
        if dates.isna().any() or dates.duplicated().any(): raise ValueError('History requires distinct valid payment_month values')
        anchor = pd.to_datetime(request.features.get('prediction_date'),errors='coerce',utc=True)
        if pd.isna(anchor) or (dates>anchor).any(): raise ValueError('History must be at or before a supplied prediction_date')
        ordered = [history[i] for i in np.argsort(dates)[-artifact['steps']:]]
        frame = pd.DataFrame([map_record(r,artifact) for r in ordered])
        return artifact['pipeline'].transform(frame)[None,:,:],frame.iloc[-1].to_dict()
    row=map_record(request.features,artifact)
    return artifact['pipeline'].transform(pd.DataFrame([row])),row

def contributions(model,X,background):
    from app.sequence import SequenceAdapter,SequenceModel
    if isinstance(model,Ensemble):
        # Calibrated outputs do not have additive raw-margin SHAP decompositions.
        return None,'ensemble_ablation'
    raw = model.model if isinstance(model,CalibratedRisk) else model
    if isinstance(raw,SequenceAdapter):
        return contributions(CalibratedRisk(raw.model,model.calibrator),X[:,-1,:],background[:,-1,:])
    if isinstance(raw,SequenceModel): return None,'sequence_ablation'
    if hasattr(raw,'coef_'):
        return (X[0]-background.mean(axis=0))*raw.coef_[0],'linear_log_odds'
    import shap
    values = np.asarray(shap.TreeExplainer(raw).shap_values(X))
    if values.ndim==3: values=values[:,:,1]
    return values[0],'tree_shap_raw_margin'

def explain(artifact,X):
    model,background=artifact['model'],artifact['background']
    try:
        values,method=contributions(model,X,background)
    except (ImportError,ValueError,TypeError,RuntimeError):
        values,method=None,'feature_ablation_fallback'
    if values is None:
        # Explicit model-output ablation; do not call this SHAP or causal evidence.
        base=float(model.predict_proba(X)[0,1])
        values=[]
        for i in range(X.shape[-1]):
            changed=X.copy()
            if X.ndim==3: changed[:,:,i]=background[:,:,i].mean(axis=0)
            else: changed[:,i]=background[:,i].mean()
            values.append(base-float(model.predict_proba(changed)[0,1]))
        values=np.asarray(values)
    names=artifact['pipeline'].get_feature_names_out()
    grouped={f:0. for f in artifact['features']}
    for name,value in zip(names,values):
        field=name.split('__',1)[-1]
        matched=next((f for f in sorted(grouped,key=len,reverse=True) if field==f or field.startswith(f+'_')),None)
        if matched: grouped[matched]+=float(value)
    drivers=[{'feature':f,'direction':'increases' if v>0 else 'decreases',
              'reason':f"{f.replace('_',' ').capitalize()} {'increased' if v>0 else 'decreased'} the model estimate relative to its reference."}
             for f,v in sorted(grouped.items(),key=lambda kv:abs(kv[1]),reverse=True)[:4] if abs(v)>1e-9]
    return {'method':method,'drivers':drivers,'limitation':'Model associations, not causal findings. Raw-margin SHAP describes the underlying model before calibration.'}

def predict(store,tid,request):
    meta,artifact=load_model(store,tid)
    X,row=transform(request,artifact)
    p=float(artifact['model'].predict_proba(X)[0,1])
    band=['LOW','MEDIUM','HIGH','VERY_HIGH'][int(np.searchsorted(store.tenant(tid)['band_edges'],p,side='right'))]
    explanation=explain(artifact,X)
    hardship=detect_hardship(request.member_text,request.declared_hardship_category)
    dpd=row.get('days_past_due')
    if dpd is not None and not np.isfinite(dpd): dpd=None
    paths=evaluate_policy(store.list(tid,'policy'),hardship,dpd)
    result={'member_id':request.member_id,'risk_probability':p,'risk_band':band,'threshold':meta['threshold'],
      'above_decision_threshold':p>=meta['threshold'],'model':meta['selected_model'],'model_version':meta['model_version'],
      'target_definition':meta['target_definition'],'reason_codes':[d['reason'] for d in explanation['drivers']],
      'explanation':explanation,'hardship_status':hardship['hardship_status'],'hardship':hardship,'approved_support_paths':paths,
      'human_review_required':band in ('HIGH','VERY_HIGH') or hardship['hardship_status']=='INFERRED_SIGNAL' or any(p['requires_human_approval'] for p in paths),
      'summary':f'The validated model estimates {band.lower()} risk for {meta["target_definition"]}. '+ ' '.join(d['reason'] for d in explanation['drivers']),
      'action_executed':False}
    store.audit(tid,'prediction.generated',{'version':meta['model_version'],'band':band})
    return result
