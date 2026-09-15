from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class TenantCreate(Strict):
    name: str = Field(min_length=2, max_length=100)
    band_edges: list[float] = Field(default_factory=lambda: [.2, .5, .75])
    @model_validator(mode='after')
    def bands(self):
        if len(self.band_edges) != 3 or not 0 < self.band_edges[0] < self.band_edges[1] < self.band_edges[2] < 1:
            raise ValueError('Provide three increasing band edges inside (0, 1)')
        return self

class DatasetRef(Strict):
    dataset_id: str

class MappingRequest(DatasetRef):
    mapping: dict[str, str] | None = None

class TrainRequest(DatasetRef):
    target_column: str = 'target_arrears'
    target_definition: str = Field(default='30+ DPD within next 90 days', min_length=5, max_length=200)
    # Explicit confirmation prevents silently treating a current-arrears flag as a future label.
    labels_confirmed: bool = False
    prediction_date_column: str | None = None
    horizon_days: int = Field(default=90, ge=1, le=730)
    candidate_models: list[str] | Literal['auto'] = 'auto'
    enable_deep_sequence_model: bool = False
    enable_ensemble: bool = True
    calibration: Literal['sigmoid', 'isotonic'] = 'sigmoid'
    threshold_objective: Literal['f1', 'minimum_recall', 'minimum_precision', 'cost'] = 'f1'
    minimum_recall: float = Field(default=.7, ge=0, le=1)
    minimum_precision: float = Field(default=.2, ge=0, le=1)
    false_negative_cost: float = Field(default=5, gt=0)
    false_positive_cost: float = Field(default=1, gt=0)
    max_false_negative_rate: float = Field(default=.5, ge=0, le=1)
    minimum_pr_auc: float = Field(default=.0, ge=0, le=1)
    metric_weights: dict[str, float] = Field(default_factory=lambda: {'pr_auc': .4, 'recall': .25, 'f1': .2, 'roc_auc': .15})
    @model_validator(mode='after')
    def weights_valid(self):
        if not self.metric_weights or set(self.metric_weights) - {'pr_auc', 'recall', 'f1', 'roc_auc', 'precision', 'calibration_score'}:
            raise ValueError('Unknown selection metric')
        if any(v < 0 for v in self.metric_weights.values()) or sum(self.metric_weights.values()) <= 0:
            raise ValueError('Metric weights must be nonnegative with positive total')
        return self

class Prediction(Strict):
    member_id: str = Field(max_length=100)
    features: dict[str, float | str | None]
    history: list[dict[str, float | str | None]] = Field(default_factory=list, max_length=120)
    member_text: str = Field(default='', max_length=10000)
    declared_hardship_category: Literal['temporary_income_disruption', 'payment_difficulty'] | None = None

class BatchPrediction(Strict):
    records: list[Prediction] = Field(min_length=1, max_length=100)

class HardshipRequest(Strict):
    text: str = Field(default='', max_length=10000)
    declared_category: Literal['temporary_income_disruption', 'payment_difficulty'] | None = None

class SupportRequest(HardshipRequest):
    days_past_due: float | None = Field(default=None, ge=0)

class Policy(Strict):
    policy_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    name: str = Field(min_length=1, max_length=150)
    max_days_past_due: float = Field(ge=0)
    hardship_categories: list[Literal['temporary_income_disruption', 'payment_difficulty']] = Field(min_length=1)
    requires_human_approval: bool = True
    active: bool = True

class PromoteRequest(Strict):
    model_version: str

class AgentRequest(Strict):
    training: TrainRequest
