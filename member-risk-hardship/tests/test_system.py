import io
import json
import time
import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings
from app.store import Store
from app.schemas import TrainRequest,Prediction
from app.data import upload,parse_upload,propose_mapping,validate_mapping
from app.training import TrainingSession,split_protocol,threshold_for
from app.inference import predict,load_model
from app.agent import TrainingAgent,predict_agent,OllamaProvider
from app.hardship import detect_hardship,evaluate_policy
from scripts.generate_demo import generate

@pytest.fixture
def store(tmp_path): return Store(tmp_path)

@pytest.fixture
def trained(store):
    tenant=store.create_tenant('Test bank',[.2,.5,.75])
    tid=tenant['tenant_id']
    dataset=upload(store,tid,generate().to_csv(index=False).encode(),'data.csv')
    req=TrainRequest(dataset_id=dataset['dataset_id'],labels_confirmed=True,candidate_models=['logistic_regression'],enable_ensemble=False)
    session=TrainingSession(store,tid,req)
    result=session.run()
    return store,tenant,session,result

def live():
    return Prediction(member_id='new',features={'loan_amount':400000,'income':65000,'late_payments':3,'missed_payments':1,'days_past_due':22})

def test_saved_inference_no_retraining(trained,monkeypatch):
    store,t,s,m=trained
    monkeypatch.setattr(TrainingSession,'run',lambda _:pytest.fail('Prediction retrained'))
    result=predict(store,t['tenant_id'],live())
    assert 0<=result['risk_probability']<=1
    assert result['model_version']==m['model_version']
    assert result['reason_codes']
    assert result['hardship_status']=='UNKNOWN'
    assert not result['approved_support_paths']
    assert m['metrics']['pr_auc']>.3
    assert sum(sum(row) for row in m['metrics']['confusion_matrix'])==m['protocol']['partition_sizes']['test']

@pytest.mark.parametrize('name',['xgboost','lightgbm','catboost'])
def test_tree_training_and_shap(store,name):
    tid=store.create_tenant('Tree bank',[.2,.5,.75])['tenant_id']
    d=upload(store,tid,generate().to_csv(index=False).encode(),'data.csv')
    session=TrainingSession(store,tid,TrainRequest(dataset_id=d['dataset_id'],labels_confirmed=True,candidate_models=[name],enable_ensemble=False))
    result=session.run()
    response=predict(store,tid,live())
    assert response['explanation']['method']=='tree_shap_raw_margin'
    assert result['selected_model']==name

def test_tenant_isolation_and_paths(trained):
    store,t,s,m=trained
    other=store.create_tenant('Other bank',[.2,.5,.75])['tenant_id']
    with pytest.raises(KeyError): store.get(other,'dataset',s.req.dataset_id)
    with pytest.raises(ValueError,match='No validated'): predict(store,other,live())
    with pytest.raises(ValueError): store.path(other,'..','..','bad')
    assert not store.list(other,'model')

def test_guardrails_and_partial_data(store):
    tid=store.create_tenant('Guardrail bank',[.2,.5,.75])['tenant_id']
    for df,expected in [(generate(20),'PARTIAL_DATA'),(generate().drop(columns='arrears_flag'),'NO_LABELS')]:
        d=upload(store,tid,df.to_csv(index=False).encode(),'d.csv')
        with pytest.raises(ValueError,match=expected): TrainingSession(store,tid,TrainRequest(dataset_id=d['dataset_id'],labels_confirmed=True)).prepare()
    df=generate();df['future_dpd']=40
    d=upload(store,tid,df.to_csv(index=False).encode(),'d.csv')
    with pytest.raises(ValueError,match='leakage'): TrainingSession(store,tid,TrainRequest(dataset_id=d['dataset_id'],labels_confirmed=True)).prepare()
    df=generate();df['race']='example';df['postcode']='x'
    mapping=propose_mapping(df);mapping['race']='payment_ratio'
    with pytest.raises(ValueError,match='Sensitive'): validate_mapping(df,mapping)
    d=upload(store,tid,df.to_csv(index=False).encode(),'d.csv')
    session=TrainingSession(store,tid,TrainRequest(dataset_id=d['dataset_id'],labels_confirmed=True))
    session.prepare()
    assert 'race' not in session.features and 'postcode' not in session.features

def test_temporal_purge():
    df=generate(4000).rename(columns={'arrears_flag':'target_arrears','cust_id':'member_id'})
    df['prediction_date']=pd.date_range('2010-01-01',periods=len(df),freq='D',tz='UTC')
    req=TrainRequest(dataset_id='x',horizon_days=90)
    parts,protocol=split_protocol(df,'target_arrears',req)
    for left,right in zip(parts[:-1],parts[1:]):
        assert df.iloc[left].prediction_date.max()+pd.Timedelta(days=90)<df.iloc[right].prediction_date.min()
        assert not set(left)&set(right)
    assert protocol['method']=='temporal_purged'

def test_threshold_constraints():
    y=np.array([0,0,0,1,1,1]);p=np.array([.01,.05,.1,.15,.2,.3])
    req=TrainRequest(dataset_id='x',threshold_objective='minimum_recall',minimum_recall=1)
    threshold=threshold_for(y,p,req)
    assert threshold<=.15 and threshold!=.5

def test_policy_requires_declared_evidence():
    policies=[{'policy_id':'P1','name':'Reschedule','hardship_categories':['temporary_income_disruption'],'max_days_past_due':60,'active':True,'requires_human_approval':True}]
    signal=detect_hardship('My salary has been delayed')
    assert signal['hardship_status']=='INFERRED_SIGNAL'
    assert evaluate_policy(policies,signal,20)==[]
    declared=detect_hardship(declared_category='temporary_income_disruption')
    assert evaluate_policy(policies,declared,20)[0]['status']=='PENDING_HUMAN_APPROVAL'
    assert evaluate_policy(policies,declared,None)==[]
    assert detect_hardship('My salary is not delayed')['hardship_status']=='UNKNOWN'

class ScriptedProvider:
    """Contract test double, explicitly not an actual LLM."""
    def __init__(self,calls): self.calls=iter(calls);self.messages=[]
    def turn(self,messages,tools):
        self.messages.append(json.dumps(messages))
        name,args=next(self.calls)
        return {'role':'assistant','content':'','tool_calls':[{'function':{'name':name,'arguments':args}}]}

def test_agent_orchestrates_tools(store):
    tid=store.create_tenant('Agent bank',[.2,.5,.75])['tenant_id']
    d=upload(store,tid,generate().to_csv(index=False).encode(),'d.csv')
    session=TrainingSession(store,tid,TrainRequest(dataset_id=d['dataset_id'],labels_confirmed=True,enable_ensemble=False))
    provider=ScriptedProvider([('inspect_dataset',{}),('map_schema',{}),('prepare_features',{}),('train_model',{'name':'logistic_regression'}),('evaluate_model',{'name':'logistic_regression'}),('compare_models',{}),('save_model',{})])
    result=TrainingAgent(session,provider).run()
    assert result['status']=='production'
    assert 'SYN-100' not in ''.join(provider.messages)
    assert len([e for e in store.events(tid) if e['event']=='agent.tool_called'])==7

def test_agent_cannot_skip_gates(store):
    tid=store.create_tenant('Agent gate',[.2,.5,.75])['tenant_id']
    agent=TrainingAgent(TrainingSession(store,tid,TrainRequest(dataset_id='x')),ScriptedProvider([]))
    with pytest.raises(ValueError,match='Inspect'): agent.dispatch('save_model',{})
    with pytest.raises(ValueError,match='Unknown'): agent.dispatch('execute_python',{'code':'bad'})

def test_agent_prediction_grounding(trained):
    store,t,s,m=trained
    provider=ScriptedProvider([('predict_risk',{}),('detect_hardship',{}),('evaluate_policy',{}),('generate_case_summary',{'reason_indices':[0]})])
    req=live();req.member_text='Private message never sent';req.member_id='PRIVATE-MEMBER'
    result=predict_agent(store,t['tenant_id'],req,provider)
    assert result['orchestration']=='llm_tools'
    assert 'PRIVATE-MEMBER' not in ''.join(provider.messages)
    assert 'Private message' not in ''.join(provider.messages)

def test_external_llm_requires_opt_in(tmp_path):
    with pytest.raises(ValueError,match='disabled'): OllamaProvider(Settings(data_dir=tmp_path,llm_url='https://remote.invalid',external_llm=False))

def test_format_parsing():
    df=generate(20)
    buffer=io.BytesIO();df.to_excel(buffer,index=False)
    assert len(parse_upload(buffer.getvalue(),'data.xlsx'))==20
    assert len(parse_upload(df.to_json(orient='records').encode(),'data.json'))==20
    with pytest.raises(ValueError): parse_upload(b'bad','model.pkl')

def test_sequence_roundtrip(tmp_path):
    from app.sequence import SequenceModel
    rng=np.random.default_rng(3)
    X=rng.normal(size=(60,6,4));y=(X[:,-1,0]>0).astype(int)
    model=SequenceModel(epochs=2).fit(X,y)
    path=tmp_path/'sequence.joblib';joblib.dump(model,path)
    restored=joblib.load(path)
    np.testing.assert_allclose(model.predict_proba(X),restored.predict_proba(X))
    np.testing.assert_allclose(restored.attention_weights(X).sum(axis=1),1,atol=1e-6)

def test_sequence_pipeline_preparation(store):
    tid=store.create_tenant('Sequence bank',[.2,.5,.75])['tenant_id']
    rows=[]
    for i,row in generate(400).iterrows():
        anchor=pd.Timestamp('2010-01-01')+pd.Timedelta(days=int(i)*10)
        for j in range(6):
            item=row.to_dict();item['payment_month']=(anchor-pd.Timedelta(days=30*(5-j))).isoformat()
            rows.append(item)
    d=upload(store,tid,pd.DataFrame(rows).to_csv(index=False).encode(),'history.csv')
    s=TrainingSession(store,tid,TrainRequest(dataset_id=d['dataset_id'],labels_confirmed=True,enable_deep_sequence_model=True,horizon_days=1,enable_ensemble=False))
    result=s.prepare()
    assert result['sequence'] and s.X.shape[:2]==(400,6)
    assert 'cnn_bilstm_attention' in result['eligible_candidates']
    s.train('cnn_bilstm_attention');s.evaluate('cnn_bilstm_attention')
    assert 'pr_auc' in s.results['cnn_bilstm_attention']['validation']

def test_ensemble_uses_same_validation(trained):
    store,t,s,m=trained
    s.req.enable_ensemble=True
    s.allowed.append('xgboost');s.train('xgboost');s.evaluate('xgboost')
    result=s.ensemble()
    assert set(result['members'])=={'logistic_regression','xgboost'}
    assert 'pr_auc' in result['validation']

def test_retraining_stages_version(trained):
    store,t,s,m=trained
    result=TrainingSession(store,t['tenant_id'],s.req).run()
    assert result['status']=='validated'
    assert load_model(store,t['tenant_id'])[0]['model_version']==m['model_version']
    store.promote(t['tenant_id'],result['model_version'])
    assert len([r for r in store.list(t['tenant_id'],'model') if r['status']=='production'])==1

def test_http_full_flow(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,admin_key='test-admin',rate_limit=1000,llm_provider='none'))
    with TestClient(app) as client:
        assert client.post('/api/v1/tenants',json={'name':'Demo'}).status_code==401
        r=client.post('/api/v1/tenants',json={'name':'Demo'},headers={'X-API-Key':'test-admin'})
        assert r.status_code==201
        tenant=r.json();root='/api/v1/tenants/'+tenant['tenant_id'];headers={'X-API-Key':tenant['api_key']}
        assert client.get(root,headers={'X-API-Key':'wrong'}).status_code==401
        r=client.post(root+'/datasets/upload',files={'file':('demo.csv',generate().to_csv(index=False),'text/csv')},headers=headers)
        assert r.status_code==201,r.text
        did=r.json()['dataset_id']
        r=client.post(root+'/training/start',json={'dataset_id':did,'labels_confirmed':True,'candidate_models':['logistic_regression'],'enable_ensemble':False},headers=headers)
        assert r.status_code==202,r.text
        jid=r.json()['job_id']
        for _ in range(300):
            job=client.get(root+'/training/'+jid,headers=headers).json()
            if job['status'] in ('completed','failed'): break
            time.sleep(.05)
        assert job['status']=='completed',job
        r=client.post(root+'/predict',json=live().model_dump(),headers=headers)
        assert r.status_code==200,r.text
        assert r.json()['model_version']==job['result']['model_version']
        assert client.get(root+'/audit',headers=headers).json()
        assert client.post(root+'/agent/predict',json=live().model_dump(),headers=headers).status_code==422
