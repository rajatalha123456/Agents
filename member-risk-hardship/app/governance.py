import numpy as np
from app.inference import load_model,map_record
from app.data import load_dataset,canonical_frame

def drift_report(store,tid,dataset_id):
    meta,artifact=load_model(store,tid)
    df,data=load_dataset(store,tid,dataset_id)
    df=canonical_frame(df,data['mapping'])
    findings=[]
    for feature,ref in artifact['reference'].items():
        if feature not in df: continue
        values=np.asarray(df[feature],dtype=float)
        values=values[np.isfinite(values)]
        if len(values)==0: continue
        shift=abs(float(values.mean())-ref['mean'])/max(ref['std'],1e-6)
        findings.append({'feature':feature,'standardized_mean_shift':shift,'flagged':shift>.5})
    report={'model_version':meta['model_version'],'features':findings,'retraining_review_recommended':any(f['flagged'] for f in findings),
       'automatically_replaced':False,'scope':'Numeric feature mean-shift screening only; label-based performance requires observed outcomes.'}
    store.audit(tid,'drift.checked',{'version':meta['model_version'],'flagged':report['retraining_review_recommended']})
    return report

def fairness_metrics(y,probabilities,groups,threshold=.5):
    """Offline controlled-audit utility; group labels never enter model features."""
    from app.training import metrics
    y,p,g=np.asarray(y),np.asarray(probabilities),np.asarray(groups)
    if not (len(y)==len(p)==len(g)): raise ValueError('Audit arrays must align')
    return {str(group):metrics(y[g==group],p[g==group],threshold) if len(np.unique(y[g==group]))==2 else {'status':'insufficient_outcomes'} for group in np.unique(g)}
