"""Run inside the final image; checks code/assets/native extensions, not a site DB."""
import importlib
import importlib.metadata
import json
import platform
from pathlib import Path

assert platform.machine() == 'aarch64', platform.machine()
bench = Path('/home/frappe/frappe-bench')
expected = {'frappe': '16.56.0', 'erpnext': '16.55.0', 'healthcare': '16.8.0', 'solvronix_desk': '3.0.1'}
versions = {}
for app in [*expected, 'smart_hospital', 'qy_vision_hospital']:
    importlib.import_module(app)
    versions[app] = importlib.metadata.version(app)
    if app in expected:
        assert versions[app] == expected[app], (app, versions[app])
assert not (bench / 'apps/tv_vision_hospital').exists()
assert not (bench / 'sites/frontend').exists()
assert (bench / 'assets/qy_vision_hospital/js/clinic_shell.js').is_file()
assert list((bench / 'assets/frappe/dist/js').glob('desk.bundle.*.js'))
assert (bench / 'assets/erpnext/banking/index.html').is_file()
manifest_path = bench / 'assets/healthcare/frontend/manifest.json'
manifest = json.loads(manifest_path.read_text())
assert manifest
for entry in manifest.values():
    if 'file' in entry:
        assert (manifest_path.parent / entry['file']).is_file(), entry['file']
portal_socket = (bench / 'apps/healthcare/patient_portal/src/socket.js').read_text()
assert 'window.location.origin' in portal_socket and 'socketio_port' not in portal_socket
rolldown = json.loads((bench / 'apps/erpnext/banking/node_modules/rolldown/package.json').read_text())
assert rolldown['version'] == '1.2.18'
for module in ['MySQLdb', 'paho.mqtt.publish', 'pyarrow', 'duckdb', 'orjson', 'PIL.Image',
               'smart_hospital.api.vision', 'smart_hospital.api.send_vision_measurement',
               'smart_hospital.api.face_identity', 'qy_vision_hospital.api.clinic_roles',
               'qy_vision_hospital.api.xml_intake']:
    importlib.import_module(module)
versions['paho-mqtt'] = importlib.metadata.version('paho-mqtt')
assert versions['paho-mqtt'] == '2.1.0'
print(json.dumps({'architecture': platform.machine(), 'versions': versions, 'code_assets_native_imports': 'PASS'}, indent=2))
