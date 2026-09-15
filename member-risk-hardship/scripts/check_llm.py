"""Verify the configured provider's real structured-tool call without member data."""
import sys
from app.agent import provider_for,tool
from app.config import Settings

def main():
    try:
        provider=provider_for(Settings())
        response=provider.turn([
            {'role':'system','content':'This is a connection test. Call connection_check with the exact value synthetic-test.'},
            {'role':'user','content':'Verify the structured tool connection. No customer data is included.'}],
            [tool('connection_check','Return the test marker.',{'marker':{'type':'string','enum':['synthetic-test']}},['marker'])])
        calls=response.get('tool_calls',[])
        if len(calls)!=1 or calls[0]['function']!={'name':'connection_check','arguments':{'marker':'synthetic-test'}}:
            raise ValueError('Provider returned an unexpected test tool call')
        print('PASS: live provider returned the expected structured tool call. No member data was sent.')
        return 0
    except ValueError as exc:
        print('NOT READY: '+str(exc))
        return 1
    except Exception as exc:
        # No raw response or request is printed, including on authentication errors.
        print('NOT READY: provider check failed ('+type(exc).__name__+').')
        return 1

if __name__=='__main__':sys.exit(main())
