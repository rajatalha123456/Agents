import json
import httpx
import pytest
from app.config import Settings
from app.openai_provider import OpenAIProvider
from app.agent import provider_for, tool

def configured():
    return Settings(llm_provider='openai',external_llm=True,openai_key='test-placeholder-not-a-real-key')

def test_requires_explicit_configuration():
    with pytest.raises(ValueError,match='ALLOW_EXTERNAL'): OpenAIProvider(Settings(external_llm=False,openai_key=''))
    with pytest.raises(ValueError,match='OPENAI_API_KEY'): OpenAIProvider(Settings(external_llm=True,openai_key=''))
    assert isinstance(provider_for(configured()),OpenAIProvider)

def test_transport_and_tool_roundtrip(monkeypatch):
    captured=[]
    def post(self,url,**kwargs):
        captured.append((url,kwargs))
        return httpx.Response(200,json={'status':'completed','output':[{'type':'function_call','id':'fc_1','call_id':'call_1','name':'inspect_dataset','arguments':'{}','status':'completed'}]})
    monkeypatch.setattr(httpx.Client,'post',post)
    provider=OpenAIProvider(configured())
    messages=[{'role':'system','content':'Use tools'},{'role':'user','content':'Inspect local data'}]
    response=provider.turn(messages,[tool('inspect_dataset','Inspect aggregates')])
    payload=captured[0][1]['json']
    assert captured[0][0]=='https://api.openai.com/v1/responses'
    assert payload['store'] is False and payload['parallel_tool_calls'] is False
    assert 'test-placeholder' not in json.dumps(payload)
    assert response['tool_calls'][0]['function']['name']=='inspect_dataset'
    messages.extend([response,{'role':'tool','tool_name':'inspect_dataset','content':'{"row_count":200}'}])
    items=provider.input_items(messages)
    assert items[-1]=={'type':'function_call_output','call_id':'call_1','output':'{"row_count":200}'}
    assert items[-2]['type']=='function_call'

def test_provider_error_is_redacted(monkeypatch):
    monkeypatch.setattr(httpx.Client,'post',lambda *a,**k:httpx.Response(401,json={'error':'sensitive provider content'}))
    with pytest.raises(ValueError,match='HTTP 401') as exc:
        OpenAIProvider(configured()).turn([],[])
    assert 'sensitive provider content' not in str(exc.value)

def test_invalid_tool_arguments_fail_closed(monkeypatch):
    monkeypatch.setattr(httpx.Client,'post',lambda *a,**k:httpx.Response(200,json={'status':'completed','output':[{'type':'function_call','name':'train_model','arguments':'not json'}]}))
    with pytest.raises(ValueError,match='invalid tool arguments'): OpenAIProvider(configured()).turn([],[])

def test_unmatched_tool_output_rejected():
    with pytest.raises(ValueError,match='Unmatched'):
        OpenAIProvider.input_items([{'role':'tool','tool_name':'save_model','content':'{}'}])

@pytest.mark.parametrize('code',['insufficient_quota','rate_limit_exceeded','credit_balance_exhausted','organization_spend_limit_exceeded','project_spend_limit_exceeded','organization_usage_limit_exceeded','slow_down'])
def test_quota_and_rate_limits_are_distinguished(monkeypatch,code):
    monkeypatch.setattr(httpx.Client,'post',lambda *a,**k:httpx.Response(429,json={'error':{'code':code,'message':'private context'}}))
    with pytest.raises(ValueError,match=code) as exc:
        OpenAIProvider(configured()).turn([],[])
    assert 'private context' not in str(exc.value)
