"""Check DeepSeek using synthetic text only; never sends mailbox/CRM data."""
import json
import pathlib
import sys
import urllib.error
import urllib.request

root = pathlib.Path(__file__).resolve().parents[1]
values = {}
for line in (root / 'deployment/model/.env').read_text(encoding='utf-8-sig').splitlines():
    if line.strip() and not line.lstrip().startswith('#') and '=' in line:
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip()
secret = values.get('DEEPSEEK_API_KEY', '')
if not secret:
    print('NOT_CONFIGURED: Fill DEEPSEEK_API_KEY locally in deployment/model/.env')
    sys.exit(2)
if values.get('MODEL_BASE_URL') != 'https://api.deepseek.com':
    print('STOPPED: Unverified endpoint; no credential transmitted.')
    sys.exit(1)
try:
    payload = {'model':values['MODEL_NAME'],'stream':False,'thinking':{'type':'disabled'},
               'max_tokens':300,'response_format':{'type':'json_object'},
               'messages':[{'role':'system','content':'Return JSON only. Extract product and quantity; do not invent paid status. Example: {"product":"example","quantity":1,"paid":null}.'},
                           {'role':'user','content':'Synthetic test: please quote 2 demo controllers. Payment has not been verified.'}]}
    request = urllib.request.Request('https://api.deepseek.com/chat/completions',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization':'Bearer '+secret,'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=int(values['MODEL_TIMEOUT_SECONDS'])) as response:
        result = json.load(response)
    content = json.loads(result['choices'][0]['message']['content'])
    if content.get('quantity') != 2 or content.get('paid') not in (None,False):
        raise ValueError('synthetic fact validation failed')
    print(json.dumps({'status':'ok','requested_model':values['MODEL_NAME'],
        'returned_model':result.get('model'),'json_valid':True,'synthetic_only':True,
        'usage':result.get('usage')},ensure_ascii=False))
except urllib.error.HTTPError as error:
    print('FAILED: HTTP',error.code,'; response/credential contents omitted.')
    sys.exit(1)
except Exception as error:
    print('FAILED:',type(error).__name__,'; credential contents omitted.')
    sys.exit(1)
