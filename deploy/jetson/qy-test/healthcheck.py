"""Health probes: HTTP, socket, RQ heartbeats and scheduler process liveness."""
import sys, os, socket, urllib.request
from pathlib import Path
mode = sys.argv[1]
if mode in ('backend', 'frontend'):
    port = 8000 if mode == 'backend' else 8080
    request = urllib.request.Request(f'http://127.0.0.1:{port}/api/method/ping', headers={'Host': os.environ['QY_SITE']})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    assert b'pong' in opener.open(request, timeout=5).read()
elif mode == 'websocket':
    with socket.create_connection(('127.0.0.1',9000),timeout=5): pass
elif mode == 'worker':
    from redis import Redis
    from rq import Worker
    from datetime import datetime, timezone
    workers = Worker.all(connection=Redis.from_url('redis://redis-queue:6379'))
    assert any(w.last_heartbeat and (datetime.now(timezone.utc)-w.last_heartbeat.replace(tzinfo=timezone.utc)).total_seconds() < 180 for w in workers)
elif mode == 'scheduler':
    assert any(b'bench' in data and b'schedule' in data for data in
               (p.read_bytes() for p in Path('/proc').glob('[0-9]*/cmdline') if p.parent.name != str(os.getpid())))
else:
    raise SystemExit('Unknown probe')
