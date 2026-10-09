"""Real Flask routes over stdin/stdout for the DOM-free JavaScript integration test."""
import os,sys,json,base64,tempfile
sys.stdin.reconfigure(encoding='utf-8');sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['AI_PROVIDER']='demo'
os.environ['IMAGE_PROVIDER']='none'
for key in ('APP_ACCESS_PASSWORD','APP_ENV','VERCEL','FRONTEND_ORIGINS'):os.environ.pop(key,None)
from app import create_app
Path('validation-output').mkdir(exist_ok=True)
temporary=tempfile.TemporaryDirectory(dir='validation-output')
client=create_app({'TESTING':True,'SECRET_KEY':'ui-integration-only','DATA_DIR':temporary.name}).test_client()
for line in sys.stdin:
    try:
        msg=json.loads(line)
        response=client.open(msg['path'],method=msg.get('method','GET'),json=msg.get('data'),headers={'X-Script2Set':'1'})
        print(json.dumps({'id':msg['id'],'status':response.status_code,'json':response.get_json(silent=True),'data':base64.b64encode(response.data).decode()}),flush=True)
    except Exception as error:print(json.dumps({'error':str(error)}),flush=True)
temporary.cleanup()
