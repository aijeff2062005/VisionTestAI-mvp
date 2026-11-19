#!/usr/bin/env bash
# Ensure .mjs is served as application/javascript (ESM + nosniff).
# Also keep nginx able to buffer large POSTs (face avatar JPEG data URLs).
set -euo pipefail
docker exec -u root visiontestai-frappe-frontend bash -lc '
  mkdir -p /tmp/nginx-client-body /var/lib/nginx/body
  chown -R frappe:frappe /tmp/nginx-client-body /var/lib/nginx
  chmod 700 /tmp/nginx-client-body /var/lib/nginx/body
  if ! grep -E "application/javascript.*mjs" /etc/nginx/mime.types >/dev/null; then
    sed -i -E "s|(application/javascript[ \t]+)([^;]+);|\1\2 mjs;|" /etc/nginx/mime.types
  fi
  if ! grep -q "\\.mjs\\$" /etc/nginx/conf.d/frappe.conf; then
    python3 - << "PY"
from pathlib import Path
p = Path("/etc/nginx/conf.d/frappe.conf")
text = p.read_text()
block = """
	location ~* ^/assets/.*\\.mjs$ {
		default_type application/javascript;
		types { }
		try_files $uri =404;
	}

"""
needle = "	location /assets {"
if ".mjs$" not in text and needle in text:
    p.write_text(text.replace(needle, block + needle, 1))
PY
  fi
  nginx -t && nginx -s reload
'
