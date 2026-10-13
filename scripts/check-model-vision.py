"""One synthetic quotation-image probe, without customer data or CRM access."""
import base64
from decimal import Decimal
import io
import json
import pathlib
import sys
import urllib.error
import urllib.request
from PIL import Image, ImageDraw, ImageFont

root = pathlib.Path(__file__).resolve().parents[1]
values = {}
for line in (root / 'deployment/model/.env').read_text(encoding='utf-8-sig').splitlines():
    if line.strip() and not line.lstrip().startswith('#') and '=' in line:
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip()
if values.get('MODEL_BASE_URL') != 'https://api.deepseek.com' or not values.get('DEEPSEEK_API_KEY'):
    print('STOPPED: official endpoint and local credential required.')
    sys.exit(1)

try:
    image = Image.new('RGB', (1200, 520), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 34)
    lines = ['SYNTHETIC QUOTATION - NOT A REAL ORDER',
             'Product: DEMO-RC-123', 'Quantity: 3 pcs', 'Unit price: USD 12.50',
             'Product subtotal: USD 37.50', 'Shipping: TBD - not yet quoted',
             'No payment information provided.']
    for i, line in enumerate(lines):
        draw.text((32, 30 + 65 * i), line, font=font, fill='black')
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    data = buffer.getvalue()
    payload = {'model':values['MODEL_NAME'],'stream':False,'thinking':{'type':'disabled'},
               'max_tokens':600,'response_format':{'type':'json_object'},
               'messages':[
                   {'role':'system','content':'Read the quotation image. Output JSON fields product,quantity,currency,unit_price,subtotal,shipping,paid. Use numeric strings for monetary values and null for unknown shipping/payment. Do not infer payment or treat shipping TBD as zero.'},
                   {'role':'user','content':[{'type':'text','text':'Extract only facts visible in this synthetic quotation image.'},
                       {'type':'image_url','image_url':{'url':'data:image/png;base64,' + base64.b64encode(data).decode('ascii'),'detail':'original'}}]}]}
    request = urllib.request.Request('https://api.deepseek.com/chat/completions',
        data=json.dumps(payload).encode('utf-8'),headers={
            'Authorization':'Bearer ' + values['DEEPSEEK_API_KEY'],'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=int(values['MODEL_TIMEOUT_SECONDS'])) as response:
        result = json.load(response)
    parsed = json.loads(result['choices'][0]['message']['content'])
    checks = {
        'model_number':parsed.get('product') == 'DEMO-RC-123',
        'quantity':str(parsed.get('quantity')) == '3',
        'currency':parsed.get('currency') == 'USD',
        'unit_price':Decimal(str(parsed.get('unit_price'))) == Decimal('12.50'),
        'subtotal':Decimal(str(parsed.get('subtotal'))) == Decimal('37.50'),
        'shipping_unknown':parsed.get('shipping') is None,
        'payment_unknown':parsed.get('paid') is None,
    }
    evidence = {'status':'ok' if all(checks.values()) else 'failed',
                'synthetic_only':True,'requested_model':values['MODEL_NAME'],
                'returned_model':result.get('model'),'checks':checks,'parsed':parsed,'usage':result.get('usage')}
    folder = root / 'records/chat-signal'
    folder.mkdir(parents=True,exist_ok=True)
    (folder / 'model-vision-synthetic.png').write_bytes(data)
    (folder / 'model-vision-verification.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps(evidence))
    if not all(checks.values()):
        sys.exit(1)
except urllib.error.HTTPError as error:
    print('FAILED: HTTP',error.code,'; credential and response omitted.')
    sys.exit(1)
except Exception as error:
    print('FAILED:',type(error).__name__,'; credential omitted.')
    sys.exit(1)
