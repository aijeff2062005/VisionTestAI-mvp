"""Read-only device/resource sampling; run beside an operator-driven measurement."""
import argparse, json, platform, subprocess, time
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--seconds',type=int,default=60)
parser.add_argument('--output',default='device-report.json')
args=parser.parse_args()
assert 1<=args.seconds<=3600

def memory():
    values={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if ':' in line and line.split()[1].isdigit()}
    values['SwapUsed']=values['SwapTotal']-values['SwapFree']
    return {k:values[k] for k in ('MemTotal','MemAvailable','SwapTotal','SwapUsed')}
def oom():
    return int(next(line.split()[1] for line in Path('/proc/vmstat').read_text().splitlines() if line.startswith('oom_kill ')))
start_oom=oom();samples=[];deadline=time.monotonic()+args.seconds
while True:
    samples.append({'timestamp':time.time(),'memory_kib':memory()})
    if time.monotonic()>=deadline:break
    time.sleep(min(2,max(0,deadline-time.monotonic())))
model=Path('/proc/device-tree/model')
report={'thresholds':'UNDECIDED; memory guardrail only','architecture':platform.machine(),'kernel':platform.release(),'os_release':Path('/etc/os-release').read_text(),'model':model.read_text().strip('\0') if model.exists() else 'not a Jetson device-tree','samples':samples,'oom_kill_delta':oom()-start_oom,'min_available_kib':min(s['memory_kib']['MemAvailable'] for s in samples),'swap_growth_kib':samples[-1]['memory_kib']['SwapUsed']-samples[0]['memory_kib']['SwapUsed'],'clinical_flow_verified':False,'physical_reboot_verified':False,'offline_fresh_install_verified':False}
report['memory_guardrail_observed']=report['min_available_kib']>=1048576 and report['oom_kill_delta']==0
Path(args.output).write_text(json.dumps(report,indent=2))
print('Saved',args.output,'; no production-readiness conclusion is implied.')
