"""Fail before deleting Git metadata if an upstream release tag moved mid-build."""
import json, subprocess
from pathlib import Path
lock=json.loads(Path('/tmp/qy-build-tools/source-lock.json').read_text())
result={}
for name, expected in lock.items():
    app=Path('/home/frappe/frappe-bench/apps')/name
    actual=subprocess.check_output(['git','-C',str(app),'rev-parse','HEAD'],text=True).strip()
    assert actual==expected['commit'], (name,actual,expected['commit'])
    result[name]={'tag':expected['tag'],'commit':actual}
Path('/home/frappe/frappe-bench/qy-source-lock.json').write_text(json.dumps(result,indent=2))
