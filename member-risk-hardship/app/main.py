from collections import defaultdict,deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import hashlib
import secrets
import threading
import time
from fastapi import FastAPI,Depends,Header,HTTPException,UploadFile,File,Request
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.config import Settings
from app.store import Store,identifier,now,digest
from app.schemas import (TenantCreate,DatasetRef,MappingRequest,TrainRequest,Prediction,BatchPrediction,
                         HardshipRequest,SupportRequest,Policy,PromoteRequest,AgentRequest)
from app import data
from app.training import TrainingSession,tenant_lock
from app.inference import predict
from app.hardship import detect_hardship,evaluate_policy
from app.governance import drift_report
from app.agent import provider_for,TrainingAgent,predict_agent

def create_app(settings=None):
    settings=settings or Settings()
    store=Store(settings.data_dir)
    executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix='risk-training')
    @asynccontextmanager
    async def lifespan(app):
        # In-process MVP worker: interrupted jobs fail visibly instead of remaining queued forever.
        with store.connect() as con:
            import json
            for tid,jid,body in con.execute("SELECT tenant,id,body FROM objects WHERE kind='job'").fetchall():
                job=json.loads(body)
                if job['status'] in ('queued','running'):
                    job.update(status='failed',error='Worker restarted; resubmit training')
                    con.execute("UPDATE objects SET body=? WHERE tenant=? AND kind='job' AND id=?",(json.dumps(job),tid,jid))
        yield
        executor.shutdown(wait=True)
    app=FastAPI(title='Member Risk & Hardship Agent',version='0.1.0',lifespan=lifespan,
      description='Tenant-specific training, calibrated inference, grounded explanations and approved support. Use X-API-Key. Interactive API console below.')
    app.state.store=store
    buckets=defaultdict(deque)
    rate_lock=threading.Lock()
    @app.middleware('http')
    async def rate_limit(request:Request,call_next):
        key=hashlib.sha256((request.headers.get('x-api-key','')+str(request.client.host if request.client else 'local')).encode()).hexdigest()
        current=time.monotonic()
        with rate_lock:
            queue=buckets[key]
            while queue and queue[0]<current-60: queue.popleft()
            if len(queue)>=settings.rate_limit: return JSONResponse({'detail':'Rate limit exceeded'},status_code=429,headers={'Retry-After':'60'})
            queue.append(current)
            if len(buckets)>10000:
                for stale in [k for k,v in buckets.items() if not v or v[-1]<current-60]: buckets.pop(stale,None)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Cache-Control']='no-store'
        return response
    @app.exception_handler(ValueError)
    async def value_error(request,exc): return JSONResponse({'detail':str(exc)},status_code=422)
    @app.exception_handler(KeyError)
    async def key_error(request,exc): return JSONResponse({'detail':'Resource not found'},status_code=404)
    def admin(x_api_key:str=Header(default='')):
        if not settings.admin_key or not secrets.compare_digest(x_api_key,settings.admin_key): raise HTTPException(401,'Valid administrator key required')
    def auth(tenant_id:str,x_api_key:str=Header(default='')):
        try: tenant=store.tenant(tenant_id)
        except KeyError: raise HTTPException(401,'Invalid tenant credentials')
        if not secrets.compare_digest(digest(x_api_key),tenant['key_hash']): raise HTTPException(401,'Invalid tenant credentials')
        return tenant_id
    @app.get('/health')
    def health(): return {'status':'ok','llm_provider':settings.llm_provider}
    static_dir=Path(__file__).parent/'static'
    if static_dir.exists():
        app.mount('/static',StaticFiles(directory=static_dir),name='static')
        @app.get('/',include_in_schema=False)
        def workspace(): return FileResponse(static_dir/'index.html')
    @app.post('/api/v1/tenants',dependencies=[Depends(admin)],status_code=201)
    def create_tenant(body:TenantCreate): return store.create_tenant(body.name,body.band_edges)
    root='/api/v1/tenants/{tenant_id}'
    @app.get(root+'/datasets')
    def datasets(tid=Depends(auth)): return store.list(tid,'dataset')
    @app.get(root+'/training')
    def training_jobs(tid=Depends(auth)): return store.list(tid,'job')
    @app.get(root)
    def get_tenant(tid=Depends(auth)):
        tenant=store.tenant(tid)
        return {k:v for k,v in tenant.items() if k!='key_hash'}
    @app.post(root+'/datasets/upload',status_code=201)
    async def upload(file:UploadFile=File(...),tid=Depends(auth)):
        content=await file.read(settings.max_upload_mb*1024*1024+1)
        await file.close()
        if len(content)>settings.max_upload_mb*1024*1024: raise HTTPException(413,'Upload too large')
        try: return data.upload(store,tid,content,file.filename or '')
        except ValueError: raise
        except Exception: raise HTTPException(422,'Unable to parse dataset')
    @app.post(root+'/datasets/profile')
    def profile(body:DatasetRef,tid=Depends(auth)): return store.get(tid,'dataset',body.dataset_id)['profile']
    @app.post(root+'/datasets/map-schema')
    def map_schema(body:MappingRequest,tid=Depends(auth)):
        df,meta=data.load_dataset(store,tid,body.dataset_id)
        meta['mapping']=data.validate_mapping(df,body.mapping or data.propose_mapping(df))
        store.put(tid,'dataset',body.dataset_id,meta)
        store.audit(tid,'schema.mapped',{'dataset_id':body.dataset_id})
        return {'mapping':meta['mapping']}
    def submit(tid,req,agent=False):
        store.get(tid,'dataset',req.dataset_id)
        provider=provider_for(settings) if agent else None
        lock=tenant_lock(tid)
        if not lock.acquire(blocking=False): raise HTTPException(409,'A training job is already running for this tenant')
        jid=identifier('train')
        job={'job_id':jid,'status':'queued','created_at':now(),'mode':'llm_tools' if agent else 'direct_tools'}
        store.put(tid,'job',jid,job)
        def work():
            try:
                job['status']='running'
                store.put(tid,'job',jid,job)
                session=TrainingSession(store,tid,req)
                result=TrainingAgent(session,provider).run() if agent else session.run()
                job.update(status='completed',result=result)
            except Exception as exc:
                # Model/library exception messages can contain raw input. Persist only known validation messages.
                job.update(status='failed',error=str(exc) if isinstance(exc,ValueError) else type(exc).__name__)
                store.audit(tid,'training.failed',{'job_id':jid,'error_type':type(exc).__name__})
            finally:
                job['finished_at']=now()
                store.put(tid,'job',jid,job)
                lock.release()
        executor.submit(work)
        return {'job_id':jid,'status':'queued'}
    @app.post(root+'/training/start',status_code=202)
    def start(body:TrainRequest,tid=Depends(auth)): return submit(tid,body)
    @app.post(root+'/agent/onboard',status_code=202)
    def onboard(body:AgentRequest,tid=Depends(auth)): return submit(tid,body.training,True)
    @app.get(root+'/training/{job_id}')
    def job(job_id:str,tid=Depends(auth)): return store.get(tid,'job',job_id)
    @app.get(root+'/models')
    def models(tid=Depends(auth)): return store.list(tid,'model')
    @app.post(root+'/models/promote')
    def promote(body:PromoteRequest,tid=Depends(auth)):
        store.promote(tid,body.model_version)
        return {'status':'production','model_version':body.model_version}
    @app.post(root+'/predict')
    def prediction(body:Prediction,tid=Depends(auth)): return predict(store,tid,body)
    @app.post(root+'/predict/batch')
    def batch(body:BatchPrediction,tid=Depends(auth)): return {'predictions':[predict(store,tid,r) for r in body.records]}
    @app.post(root+'/agent/predict')
    def agent_predict(body:Prediction,tid=Depends(auth)): return predict_agent(store,tid,body,provider_for(settings))
    @app.post(root+'/hardship/analyze')
    def hardship(body:HardshipRequest,tid=Depends(auth)): return detect_hardship(body.text,body.declared_category)
    @app.post(root+'/hardship/support-options')
    def support(body:SupportRequest,tid=Depends(auth)):
        signal=detect_hardship(body.text,body.declared_category)
        return {'hardship':signal,'approved_support_paths':evaluate_policy(store.list(tid,'policy'),signal,body.days_past_due)}
    @app.post(root+'/policies',status_code=201)
    def policy(body:Policy,tid=Depends(auth)):
        store.put(tid,'policy',body.policy_id,body.model_dump())
        store.audit(tid,'policy.configured',{'policy_id':body.policy_id})
        return body
    @app.get(root+'/policies')
    def policies(tid=Depends(auth)): return store.list(tid,'policy')
    @app.get(root+'/audit')
    def audit(tid=Depends(auth)): return store.events(tid)
    @app.post(root+'/monitoring/drift')
    def drift(body:DatasetRef,tid=Depends(auth)): return drift_report(store,tid,body.dataset_id)
    return app

app=create_app()
