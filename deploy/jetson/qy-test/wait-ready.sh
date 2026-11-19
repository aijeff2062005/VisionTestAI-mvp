#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export READY_TIMEOUT_SECONDS="${READY_TIMEOUT_SECONDS:-1800}"
python3 - <<'PY'
import subprocess, json, time, os
expected={'db','redis-cache','redis-queue','mqtt','backend','frontend','worker','scheduler','websocket'}
deadline=time.monotonic()+int(os.environ['READY_TIMEOUT_SECONDS'])
while time.monotonic()<deadline:
    output=subprocess.check_output(['docker','compose','--env-file','.env','ps','--all','--format','json'],text=True)
    try: rows=json.loads(output); rows=rows if isinstance(rows,list) else [rows]
    except json.JSONDecodeError: rows=[json.loads(line) for line in output.splitlines() if line]
    mapping={r['Service']:r for r in rows}
    for name in ('configurator','provision'):
        r=mapping.get(name,{})
        if r.get('State')=='exited' and r.get('ExitCode',0)!=0: raise SystemExit(f'{name} failed: inspect docker compose logs {name}')
    if expected <= mapping.keys() and all(mapping[n].get('State')=='running' and mapping[n].get('Health')=='healthy' for n in expected):
        print('All nine long-running services healthy'); break
    time.sleep(5)
else: raise SystemExit('Health timeout; data retained; inspect docker compose ps -a and logs')
PY
