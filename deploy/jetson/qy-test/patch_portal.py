"""Route Healthcare Portal Socket.IO through the same frontend origin."""
from pathlib import Path
import sys

path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/home/frappe/frappe-bench/apps/healthcare/patient_portal/src/socket.js')
s = path.read_text()
import_line = "import { socketio_port } from '../../../../sites/common_site_config.json'\n"
old = """\tlet host = window.location.hostname
\tlet siteName = window.site_name || host
\tlet port = window.location.port ? `:${socketio_port}` : ''
\tlet protocol = port ? 'http' : 'https'
\tlet url = `${protocol}://${host}${port}/${siteName}`"""
new = """\tlet siteName = window.site_name || window.location.hostname
\tlet url = `${window.location.origin}/${siteName}`"""
assert s.count(import_line) == 1 and s.count(old) == 1, 'Healthcare socket source changed; inspect before patching'
path.write_text(s.replace(import_line, '').replace(old, new))
