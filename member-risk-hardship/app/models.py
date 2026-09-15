from typing import Protocol
import numpy as np
from sklearn.linear_model import LogisticRegression

class RiskModel(Protocol):
    def fit(self, X, y): ...
    def predict_proba(self, X): ...

TABULAR = ['logistic_regression', 'xgboost', 'lightgbm', 'catboost']

def build_model(name, y):
    ratio = float((y == 0).sum() / max(1, (y == 1).sum()))
    if name == 'logistic_regression':
        return LogisticRegression(max_iter=1000, class_weight='balanced', random_state=42)
    if name == 'xgboost':
        from xgboost import XGBClassifier
        return XGBClassifier(n_estimators=120, max_depth=3, learning_rate=.05, scale_pos_weight=ratio, n_jobs=1, random_state=42, eval_metric='logloss')
    if name == 'lightgbm':
        from lightgbm import LGBMClassifier
        return LGBMClassifier(n_estimators=120, max_depth=4, num_leaves=15, learning_rate=.05, class_weight='balanced', n_jobs=1, random_state=42, verbosity=-1)
    if name == 'catboost':
        from catboost import CatBoostClassifier
        return CatBoostClassifier(iterations=120, depth=4, learning_rate=.05, auto_class_weights='Balanced', random_seed=42, verbose=False, thread_count=1, allow_writing_files=False)
    raise ValueError(f'Unknown candidate: {name}')

class ProbabilityCalibrator:
    def __init__(self, method='sigmoid'):
        self.method = method
    @staticmethod
    def logits(p):
        p = np.clip(p, 1e-6, 1-1e-6)
        return np.log(p/(1-p)).reshape(-1, 1)
    def fit(self, p, y):
        if self.method == 'isotonic':
            from sklearn.isotonic import IsotonicRegression
            self.model = IsotonicRegression(out_of_bounds='clip').fit(p, y)
        else:
            self.model = LogisticRegression(C=1e6).fit(self.logits(p), y)
            if self.model.coef_[0,0] <= 0:
                raise ValueError('Calibration reverses model ranking; candidate rejected')
        return self
    def predict(self, p):
        return self.model.predict(p) if self.method == 'isotonic' else self.model.predict_proba(self.logits(p))[:,1]

class CalibratedRisk:
    def __init__(self, model, calibrator):
        self.model, self.calibrator = model, calibrator
    def predict_proba(self, X):
        p = self.calibrator.predict(self.model.predict_proba(X)[:,1])
        return np.column_stack([1-p, p])

class Ensemble:
    def __init__(self, models, weights):
        self.models, self.weights = models, np.array(weights)/sum(weights)
    def predict_proba(self, X):
        return np.average([m.predict_proba(X) for m in self.models], weights=self.weights, axis=0)
