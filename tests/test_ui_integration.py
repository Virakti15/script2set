import os,sys,subprocess,json
from pathlib import Path

def test_real_ui_handlers_and_flask_workflow():
    test=Path(__file__).with_name('ui_workflow.cjs')
    result=subprocess.run(['node',str(test)],env={**os.environ,'TEST_PYTHON':sys.executable},capture_output=True,text=True,encoding='utf-8',timeout=60)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    report=json.loads(result.stdout)
    assert report['passed']>=15
