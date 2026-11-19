"""Apply audited build-only cache/network/asset settings to the pinned recipe."""
from pathlib import Path
import sys

path = Path(sys.argv[1])
s = path.read_text()
s = s.replace('    libpq-dev ', '    libpq5 ', 1)
needle = 'RUN --mount=type=secret,id=apps_json,target=/opt/frappe/apps.json,uid=1000,gid=0 '
assert s.count(needle) == 1, 'Upstream recipe changed: inspect secret mount before building'
mounts = '''RUN --mount=type=cache,id=qy-frappe-arm64-deps,target=/home/frappe/.cache,uid=1000,gid=0,sharing=locked \\
    --mount=type=bind,source=dependency-cache,target=/opt/dependency-cache \\
    --mount=type=secret,id=apps_json,target=/opt/frappe/apps.json,uid=1000,gid=0 '''
s = s.replace(needle, mounts)
needle = '  : "${CACHE_BUST}" && '
assert s.count(needle) == 1
s = s.replace(needle, '''  cp -an /opt/dependency-cache/. /home/frappe/.cache/ && \\
  yarn config set network-timeout 600000 && \\
  yarn config set registry https://registry.npmjs.org && \\
  : "${CACHE_BUST}" && ''')
s = s.replace('    --verbose \\\n', '')
s = s.replace('    --skip-redis-config-generation \\\n', '    --skip-redis-config-generation \\\n    --skip-assets \\\n')
cleanup = '''  echo "{}" > sites/common_site_config.json && \\
  find apps -mindepth 1 -path "*/.git" | xargs rm -fr && \\
  chmod -R g=u /home/frappe/frappe-bench'''
assert s.count(cleanup) == 1
s = s.replace(cleanup, '  echo "{}" > sites/common_site_config.json')
assets = '''COPY --chown=frappe:0 qy-build-tools/ /tmp/qy-build-tools/
# Separate asset compilation so an bundler failure keeps installed apps cached.
# Rolldown 1.2.16 can stall under QEMU; 1.2.18 remains within Vite 8.2.4's ~1.2.4 range.
RUN --mount=type=cache,id=qy-frappe-arm64-deps,target=/home/frappe/.cache,uid=1000,gid=0,sharing=locked \\
  cd /home/frappe/frappe-bench && \
  printf '{"socketio_port":9000}\\n' > sites/common_site_config.json && \
  python3 /tmp/qy-build-tools/patch_portal.py && \
  python3 /tmp/qy-build-tools/verify_sources.py && \
  cd apps/erpnext/banking && \\
  yarn add --dev --exact --ignore-scripts rolldown@1.2.18 && \\
  cd /home/frappe/frappe-bench && \\
  ROLLDOWN_WORKER_THREADS=2 TOKIO_WORKER_THREADS=2 RAYON_NUM_THREADS=2 UV_THREADPOOL_SIZE=2 bench build && \\
  ./env/bin/python -c 'import json; from pathlib import Path; p=Path("apps/erpnext/banking/node_modules/rolldown/package.json"); Path("qy-build-tools.json").write_text(json.dumps({"rolldown":json.loads(p.read_text())["version"]}))' && \
  rm -rf apps/erpnext/banking/node_modules apps/erpnext/node_modules apps/healthcare/patient_portal/node_modules && \
  cd apps/frappe && yarn install --production --frozen-lockfile --ignore-scripts && cd ../.. && \
  find apps -mindepth 1 -path "*/.git" | xargs rm -fr && \\
  chmod -R g=u /home/frappe/frappe-bench

'''
assert s.count('FROM base AS backend') == 1
s = s.replace('FROM base AS backend', assets + 'FROM base AS backend')
path.write_text(s)
