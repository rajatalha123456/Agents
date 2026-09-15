from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings

def test_frontend_and_scoped_lists(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,admin_key='frontend-test',llm_provider='none'))
    with TestClient(app) as c:
        page=c.get('/')
        assert page.status_code==200 and 'Member risk workspace' in page.text
        assert c.get('/static/app.js').status_code==200
        assert c.get('/static/styles.css').status_code==200
        assert c.get('/static/../.env').status_code==404
        tenant=c.post('/api/v1/tenants',headers={'X-API-Key':'frontend-test'},json={'name':'Frontend test'}).json()
        base='/api/v1/tenants/'+tenant['tenant_id']
        for path in ['/datasets','/training']:
            assert c.get(base+path).status_code==401
            assert c.get(base+path,headers={'X-API-Key':tenant['api_key']}).json()==[]
