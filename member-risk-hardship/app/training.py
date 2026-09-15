import os
from threading import Lock
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import (average_precision_score, roc_auc_score, precision_score, recall_score,
 f1_score, confusion_matrix, brier_score_loss, accuracy_score, balanced_accuracy_score)
from app.data import load_dataset, canonical_frame, approved_features, NUMERIC
from app.models import TABULAR, build_model, ProbabilityCalibrator, CalibratedRisk, Ensemble
from app.store import identifier, now

LOCKS: dict[str, Lock] = {}
LOCK_GUARD = Lock()

def tenant_lock(tid):
    with LOCK_GUARD:
        return LOCKS.setdefault(tid, Lock())

def metrics(y, p, threshold):
    pred = p >= threshold
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0,1]).ravel()
    ece = 0.
    for a,b in zip(np.linspace(0,1,11)[:-1], np.linspace(0,1,11)[1:]):
        mask = (p >= a) & ((p < b) if b < 1 else (p <= b))
        if mask.any(): ece += mask.mean() * abs(p[mask].mean()-np.asarray(y)[mask].mean())
    return {'pr_auc': float(average_precision_score(y,p)), 'roc_auc': float(roc_auc_score(y,p)),
      'precision': float(precision_score(y,pred,zero_division=0)), 'recall': float(recall_score(y,pred,zero_division=0)),
      'f1': float(f1_score(y,pred,zero_division=0)), 'false_negative_rate': float(fn/max(1,fn+tp)),
      'brier_score': float(brier_score_loss(y,p)), 'calibration_score': float(1-brier_score_loss(y,p)),
      'calibration_error': float(ece), 'accuracy': float(accuracy_score(y,pred)),
      'balanced_accuracy': float(balanced_accuracy_score(y,pred)), 'specificity': float(tn/max(1,tn+fp)),
      'confusion_matrix': [[int(tn),int(fp)],[int(fn),int(tp)]]}

def threshold_for(y, p, req):
    options = []
    for t in np.unique(np.r_[np.linspace(.01,.99,99), p]):
        pred = p >= t
        recall = recall_score(y,pred,zero_division=0)
        precision = precision_score(y,pred,zero_division=0)
        if 1-recall > req.max_false_negative_rate: continue
        if req.threshold_objective == 'minimum_recall' and recall < req.minimum_recall: continue
        if req.threshold_objective == 'minimum_precision' and precision < req.minimum_precision: continue
        if req.threshold_objective == 'minimum_recall': score = precision
        elif req.threshold_objective == 'minimum_precision': score = recall
        elif req.threshold_objective == 'cost':
            score = -(req.false_negative_cost*np.sum((y==1)&~pred)+req.false_positive_cost*np.sum((y==0)&pred))
        else: score = f1_score(y,pred,zero_division=0)
        options.append((float(score),float(t)))
    if not options: raise ValueError('No threshold satisfies configured constraints')
    return max(options)[1]

def split_protocol(frame, target, req):
    date_col = req.prediction_date_column or ('prediction_date' if 'prediction_date' in frame else None)
    if date_col:
        if date_col not in frame: raise ValueError('Prediction date column not found')
        dates = pd.to_datetime(frame[date_col], errors='coerce', utc=True)
        if dates.isna().any(): raise ValueError('Invalid prediction dates')
        unique = np.sort(dates.unique())
        if len(unique) < 20: raise ValueError('Insufficient distinct prediction dates')
        cut = [unique[int(len(unique)*f)] for f in (.5,.65,.8)]
        gap = pd.Timedelta(days=req.horizon_days)
        parts = [np.where(dates < cut[0]-gap)[0], np.where((dates >= cut[0]) & (dates < cut[1]-gap))[0],
                 np.where((dates >= cut[1]) & (dates < cut[2]-gap))[0], np.where(dates >= cut[2])[0]]
        protocol = {'method':'temporal_purged', 'horizon_embargo_days':req.horizon_days,
                    'boundaries':[str(c) for c in cut], 'limitation': 'Labels must be observed through the full future horizon; caller attests labels_confirmed.'}
        if 'member_id' in frame:
            # Entirely exclude members shared with later partitions.
            seen = set()
            for i in reversed(range(4)):
                parts[i] = np.array([j for j in parts[i] if frame.iloc[j]['member_id'] not in seen], dtype=int)
                seen.update(frame.iloc[parts[i]]['member_id'])
    else:
        if 'member_id' in frame and frame.member_id.duplicated().any():
            raise ValueError('Repeated members require dated sequence preparation; random row splits are prohibited')
        indices = np.arange(len(frame))
        fit, rest = train_test_split(indices, test_size=.5, stratify=frame[target], random_state=42)
        cal, rest = train_test_split(rest, test_size=.7, stratify=frame.iloc[rest][target], random_state=43)
        val, test = train_test_split(rest, test_size=4/7, stratify=frame.iloc[rest][target], random_state=44)
        parts = [fit,cal,val,test]
        protocol = {'method':'stratified_no_dates', 'limitation':'Temporal generalization is unverified because no snapshot dates were provided.'}
    for name, idx in zip(['fit','calibration','validation','test'],parts):
        counts = frame.iloc[idx][target].value_counts()
        if len(idx) < 20 or len(counts) != 2 or counts.min() < 3:
            raise ValueError(f'Insufficient data/classes in {name} partition after leakage controls')
    protocol['partition_sizes'] = dict(zip(['fit','calibration','validation','test'],map(len,parts)))
    return parts,protocol

class TrainingSession:
    """The direct API and LLM tool dispatcher both call this gated lifecycle."""
    def __init__(self, store, tid, req):
        self.store,self.tid,self.req = store,tid,req
        self.results, self.models, self.errors = {},{},{}
        self.prepared = False
    def inspect(self):
        _,meta = load_dataset(self.store,self.tid,self.req.dataset_id)
        return meta['profile']
    def map_schema(self, mapping=None):
        from app.data import validate_mapping
        df,meta = load_dataset(self.store,self.tid,self.req.dataset_id)
        if mapping:
            meta['mapping'] = validate_mapping(df,mapping)
            self.store.put(self.tid,'dataset',self.req.dataset_id,meta)
        return meta['mapping']
    def prepare(self):
        if not self.req.labels_confirmed:
            raise ValueError('Confirm labels represent the configured future outcome and are fully observed')
        df, self.dataset = load_dataset(self.store,self.tid,self.req.dataset_id)
        self.mapping = self.dataset['mapping']
        df = canonical_frame(df,self.mapping)
        target = self.mapping.get(self.req.target_column,self.req.target_column)
        if target not in df or df[target].notna().sum() == 0: raise ValueError('NO_LABELS: supervised training requires outcome labels')
        if df[target].isna().any() or not set(df[target].unique()) <= {0,1}: raise ValueError('Outcome labels must be complete binary 0/1 values')
        if len(df) < 200 or df[target].value_counts().min() < 30 or df[target].nunique() != 2:
            raise ValueError('PARTIAL_DATA: need at least 200 rows and 30 outcomes per class')
        self.features = approved_features(df,self.mapping,target)
        self.sequence = self.req.enable_deep_sequence_model
        self.steps = 6
        windows = None
        if self.sequence:
            if not {'member_id','payment_month'} <= set(df): raise ValueError('Sequence training needs member_id and payment_month')
            df['payment_month'] = pd.to_datetime(df.payment_month,errors='coerce',utc=True)
            if df.payment_month.isna().any() or df.duplicated(['member_id','payment_month']).any(): raise ValueError('Invalid or duplicate sequence timestamps')
            samples, windows = [],[]
            for _, group in df.sort_values('payment_month').groupby('member_id'):
                if len(group) < self.steps: continue
                history = group.tail(self.steps)
                # Last row is the observation anchor; all inputs are at/before that anchor.
                anchor = history.iloc[-1].copy()
                anchor['prediction_date'] = anchor['payment_month']
                samples.append(anchor)
                windows.append(history[self.features])
            df = pd.DataFrame(samples).reset_index(drop=True)
            if len(df) < 200: raise ValueError('Sequence model needs at least 200 members with six historical observations')
        elif 'payment_month' in df and 'member_id' in df and df.member_id.duplicated().any():
            raise ValueError('Repeated payment histories require enable_deep_sequence_model for aligned member windows')
        split_req = self.req.model_copy(update={'prediction_date_column':self.mapping.get(self.req.prediction_date_column,self.req.prediction_date_column)})
        self.parts,self.protocol = split_protocol(df,target,split_req)
        nums = [f for f in self.features if f in NUMERIC]
        cats = [f for f in self.features if f not in NUMERIC]
        self.pipeline = ColumnTransformer([
          ('numeric',Pipeline([('impute',SimpleImputer(strategy='median',keep_empty_features=True)),('scale',StandardScaler())]),nums),
          ('categorical',Pipeline([('impute',SimpleImputer(strategy='most_frequent')),('encode',OneHotEncoder(handle_unknown='ignore',sparse_output=False))]),cats)], verbose_feature_names_out=True)
        fit = self.parts[0]
        fitting = pd.concat([windows[i] for i in fit],ignore_index=True) if self.sequence else df.iloc[fit][self.features]
        self.pipeline.fit(fitting)
        self.X = np.stack([self.pipeline.transform(w) for w in windows]) if self.sequence else self.pipeline.transform(df[self.features])
        self.y = df[target].to_numpy(dtype=int)
        self.reference = {f:{'mean':float(df[f].mean()),'std':float(df[f].std() or 1)} for f in nums if df[f].notna().any()}
        self.background = self.X[fit[:min(100,len(fit))]]
        requested = self.req.candidate_models
        self.allowed = TABULAR.copy()
        if self.sequence: self.allowed.append('cnn_bilstm_attention')
        if requested != 'auto':
            if not requested or set(requested)-set(self.allowed): raise ValueError('Invalid or ineligible model candidates')
            self.allowed = list(dict.fromkeys(requested))
        self.prepared = True
        return {'features':self.features,'eligible_candidates':self.allowed,'protocol':self.protocol, 'sequence':self.sequence}
    def train(self,name):
        if not self.prepared: raise ValueError('Prepare features before training')
        if name not in self.allowed: raise ValueError('Candidate is not approved for this dataset')
        if name in self.models: return {'model':name,'status':'already_trained'}
        fit,cal,_,_ = self.parts
        if name == 'cnn_bilstm_attention':
            from app.sequence import SequenceModel
            model = SequenceModel(self.steps).fit(self.X[fit],self.y[fit])
        else:
            model = build_model(name,self.y[fit])
            model.fit(self.X[fit,-1,:] if self.sequence else self.X[fit],self.y[fit])
            if self.sequence:
                from app.sequence import SequenceAdapter
                model = SequenceAdapter(model)
        calibrator = ProbabilityCalibrator(self.req.calibration).fit(model.predict_proba(self.X[cal])[:,1],self.y[cal])
        self.models[name] = CalibratedRisk(model,calibrator)
        self.store.audit(self.tid,'candidate.trained',{'model':name})
        return {'model':name,'status':'trained','calibration':self.req.calibration}
    def evaluate(self,name):
        if name not in self.models: raise ValueError('Train candidate before evaluating')
        val = self.parts[2]
        p = self.models[name].predict_proba(self.X[val])[:,1]
        t = threshold_for(self.y[val],p,self.req)
        m = metrics(self.y[val],p,t)
        score = sum(m[k]*v for k,v in self.req.metric_weights.items())/sum(self.req.metric_weights.values())
        self.results[name] = {'threshold':t,'validation':m,'selection_score':score}
        return self.results[name]
    def ensemble(self):
        if not self.req.enable_ensemble or len(self.results)<2: return {'status':'not_eligible'}
        names = sorted(self.results,key=lambda n:self.results[n]['selection_score'],reverse=True)[:3]
        model = Ensemble([self.models[n] for n in names],[max(.001,self.results[n]['selection_score']) for n in names])
        # Members are already calibrated; ensemble is compared on the same validation partition.
        self.models['ensemble'] = model
        result = self.evaluate('ensemble')
        result['members'] = names
        return result
    def compare(self):
        if not self.results: raise ValueError('No evaluated candidates; failures: '+str(self.errors))
        eligible = [n for n,r in self.results.items() if r['validation']['pr_auc'] >= max(self.req.minimum_pr_auc,float(self.y[self.parts[2]].mean())) and r['validation']['false_negative_rate'] <= self.req.max_false_negative_rate]
        if not eligible: raise ValueError('No candidate passes validation gates')
        self.selected = max(eligible,key=lambda n:(self.results[n]['selection_score'],n != 'ensemble'))
        return {'selected_model':self.selected,'candidates':self.results,'failed_candidates':self.errors}
    def save(self):
        if not hasattr(self,'selected'): raise ValueError('Compare evaluated candidates before saving')
        if hasattr(self,'saved'): return self.saved
        test = self.parts[3]
        selected = self.results[self.selected]
        # Test is opened once, after all model/threshold selection. It never chooses the winner.
        test_results = {n:metrics(self.y[test],m.predict_proba(self.X[test])[:,1],self.results[n]['threshold']) for n,m in self.models.items() if n in self.results}
        test_metrics = test_results[self.selected]
        if test_metrics['pr_auc'] < max(self.req.minimum_pr_auc,float(self.y[test].mean())) or test_metrics['false_negative_rate'] > self.req.max_false_negative_rate:
            raise ValueError('Selected candidate failed untouched test acceptance gates; no model deployed')
        if self.selected == 'ensemble' and test_metrics['pr_auc'] <= max(test_results[n]['pr_auc'] for n in selected['members']):
            raise ValueError('Ensemble did not improve held-out test PR-AUC; rerun without ensemble after review')
        version = identifier('v')
        artifact = {'model':self.models[self.selected],'pipeline':self.pipeline,'features':self.features,'mapping':self.mapping,
                    'background':self.background,'sequence':self.sequence,'steps':self.steps,'threshold':selected['threshold'],'reference':self.reference}
        path = self.store.path(self.tid,'models',version+'.joblib')
        joblib.dump(artifact,str(path)+'.tmp')
        os.replace(str(path)+'.tmp',path)
        import hashlib
        artifact_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        body = {'model_version':version,'selected_model':self.selected,'status':'validated','training_timestamp':now(),
                'training_dataset_hash':self.dataset['sha256'],'dataset_id':self.req.dataset_id,'feature_schema_version':'1',
                'target_definition':self.req.target_definition,'target_column':self.req.target_column,
                'metrics':test_metrics,'all_test_metrics':test_results,'candidates':self.results,'failed_candidates':self.errors,
                'threshold':selected['threshold'],'calibration_method':self.req.calibration,'protocol':self.protocol,
                'features':self.features,'artifact_sha256':artifact_hash,'sequence':self.sequence}
        self.store.put(self.tid,'model',version,body)
        # Retraining is staged for human promotion; never silently replace an incumbent.
        if not any(m['status']=='production' for m in self.store.list(self.tid,'model')):
            self.store.promote(self.tid,version)
            body['status']='production'
        self.store.audit(self.tid,'model.saved',{'version':version,'model':self.selected,'metrics':test_metrics})
        self.saved = body
        return body
    def run(self):
        self.prepare()
        for name in self.allowed:
            try:
                self.train(name)
                self.evaluate(name)
            except (ImportError,ValueError,RuntimeError) as exc:
                self.errors[name] = type(exc).__name__
        self.ensemble()
        self.compare()
        return self.save()
