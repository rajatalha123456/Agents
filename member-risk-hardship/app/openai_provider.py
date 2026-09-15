"""OpenAI Responses transport for the shared bounded tool orchestrator."""
import json
import httpx

class OpenAIProvider:
    def __init__(self, settings):
        if not settings.external_llm:
            raise ValueError('OpenAI requires ALLOW_EXTERNAL_LLM=true for aggregate tool context')
        if not settings.openai_key.strip():
            raise ValueError('Set OPENAI_API_KEY in the local environment')
        self.settings = settings

    @staticmethod
    def input_items(messages):
        items, pending = [], []
        for message in messages:
            if message['role'] == 'assistant' and '_openai_output' in message:
                output = message['_openai_output']
                items.extend(output)
                pending.extend((x['name'], x['call_id']) for x in output if x['type'] == 'function_call')
            elif message['role'] == 'tool':
                if not pending or pending[0][0] != message['tool_name']:
                    raise ValueError('Unmatched OpenAI function output')
                _, call_id = pending.pop(0)
                items.append({'type':'function_call_output','call_id':call_id,'output':message['content']})
            else:
                items.append({'role':message['role'],'content':message.get('content','')})
        if pending:
            raise ValueError('Missing OpenAI function results')
        return items

    def turn(self, messages, tools):
        payload = {
            'model':self.settings.openai_model,
            'input':self.input_items(messages),
            # Dynamic schema mappings use additionalProperties; deterministic local
            # JSON-schema validation remains mandatory instead of strict API mode.
            'tools':[{'type':'function', **t['function'], 'strict':False} for t in tools],
            'tool_choice':'required', 'parallel_tool_calls':False,
            'store':False, 'max_output_tokens':4096,
        }
        try:
            with httpx.Client(timeout=120, follow_redirects=False) as client:
                response = client.post('https://api.openai.com/v1/responses',
                    headers={'Authorization':'Bearer '+self.settings.openai_key}, json=payload)
                if response.status_code >= 400:
                    # Never include provider bodies, request context or credentials in logs.
                    try:
                        error_code=response.json().get('error',{}).get('code')
                    except (ValueError,AttributeError):
                        error_code=None
                    quota_errors={
                        'credit_balance_exhausted':'The organization has no prepaid API credits remaining. Check API billing.',
                        'organization_spend_limit_exceeded':'The organization spend limit has been reached. Review billing limits.',
                        'project_spend_limit_exceeded':'The project spend limit has been reached. Review project limits.',
                        'organization_usage_limit_exceeded':'The organization usage limit has been reached. Review approved usage limits.',
                        'slow_down':'Request traffic increased too quickly. Wait before retrying.',
                    }
                    if response.status_code==429 and error_code in quota_errors:
                        raise ValueError('OpenAI '+error_code+' (HTTP 429): '+quota_errors[error_code])
                    if response.status_code==429 and error_code=='insufficient_quota':
                        raise ValueError('OpenAI insufficient_quota (HTTP 429): check API billing credits and organization usage limits. No automatic retry was made.')
                    if response.status_code==429 and error_code=='rate_limit_exceeded':
                        raise ValueError('OpenAI rate_limit_exceeded (HTTP 429): wait before retrying or review project rate limits.')
                    raise ValueError(f'OpenAI request failed (HTTP {response.status_code}); check credentials, model access and billing')
                body = response.json()
        except httpx.HTTPError:
            raise ValueError('OpenAI connection failed; check network connectivity') from None
        if body.get('status') != 'completed':
            raise ValueError('OpenAI response did not complete; no tool executed')
        output = body.get('output', [])
        calls = []
        for item in output:
            if item.get('type') == 'function_call':
                try:
                    arguments = json.loads(item['arguments'])
                except (KeyError,TypeError,ValueError):
                    raise ValueError('OpenAI returned invalid tool arguments') from None
                calls.append({'function':{'name':item['name'],'arguments':arguments}})
        if len(calls) != 1:
            raise ValueError('OpenAI must return exactly one workflow tool call')
        return {'role':'assistant','content':'','tool_calls':calls,'_openai_output':output}
