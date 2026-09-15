"""Run against a local server with synthetic records; credentials are not logged."""
import json
import argparse
import os
import time
from pathlib import Path
import httpx
from dotenv import load_dotenv
load_dotenv()

def main():
    parser=argparse.ArgumentParser(description='Run synthetic onboarding and prediction through the local API.')
    parser.add_argument('--agent',action='store_true',help='Use the configured real LLM for both workflows')
    args=parser.parse_args()
    with httpx.Client(base_url=os.getenv('RISK_API_URL','http://127.0.0.1:8000'),timeout=60) as client:
        r=client.post('/api/v1/tenants',headers={'X-API-Key':os.environ['ADMIN_API_KEY']},json={'name':'Synthetic Demo Bank'})
        r.raise_for_status(); tenant=r.json()
        print(json.dumps({k:v for k,v in tenant.items() if k!='api_key'},indent=2))
        client.headers['X-API-Key']=tenant['api_key']
        root='/api/v1/tenants/'+tenant['tenant_id']
        with Path('sample_data/historical.csv').open('rb') as f:
            r=client.post(root+'/datasets/upload',files={'file':('historical.csv',f,'text/csv')})
        r.raise_for_status(); did=r.json()['dataset_id']
        training={'dataset_id':did,'target_column':'arrears_flag','labels_confirmed':True,'enable_ensemble':False}
        r=client.post(root+('/agent/onboard' if args.agent else '/training/start'),json={'training':training} if args.agent else training)
        r.raise_for_status(); jid=r.json()['job_id']
        for _ in range(300):
            job=client.get(root+'/training/'+jid).json()
            if job['status'] in ('completed','failed'): break
            time.sleep(1)
        if job['status']!='completed': raise RuntimeError(job)
        print('Model:',job['result']['selected_model'],'Metrics:',job['result']['metrics'])
        r=client.post(root+('/agent/predict' if args.agent else '/predict'),timeout=600,json={'member_id':'SYN-LIVE','features':{'loan_amount':400000,'income':75000,'late_payments':3,'missed_payments':1,'days_past_due':22}})
        r.raise_for_status(); print(json.dumps(r.json(),indent=2))

if __name__=='__main__': main()
