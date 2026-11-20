"""Run inside backend. Uses only synthetic acceptance data on the isolated site."""
import os, json, time, io
from pathlib import Path
import frappe
os.chdir('/home/frappe/frappe-bench/sites')
frappe.init(site=os.environ['QY_SITE'])
frappe.connect()
try:
    apps = frappe.get_installed_apps()
    assert set(apps) == {'frappe','erpnext','healthcare','solvronix_desk','smart_hospital','qy_vision_hospital'}, apps
    assert frappe.db.exists('Page','visioncare')
    assert frappe.is_setup_complete(), 'Setup wizard must be completed by installer'
    from frappe.utils.file_manager import save_file
    marker = 'qy-release-acceptance.txt'
    metadata = Path(frappe.get_site_path('private','qy-acceptance-marker.json'))
    recorded = json.loads(metadata.read_text()) if metadata.exists() else {}
    existing = recorded.get('file_id')
    if existing and not frappe.db.exists('File', existing): existing = None
    if os.environ.get('BREAK_PERSISTENCE') == '1':
        assert existing
        frappe.delete_doc('File', existing)
        frappe.db.commit()
        assert not frappe.db.exists('File', existing)
        print('Synthetic acceptance file removed before restore drill')
    elif os.environ.get('CHECK_PERSISTENCE') == '1':
        assert existing, 'File row missing after restart/restore'
        document=frappe.get_doc('File',existing)
        assert Path(document.get_full_path()).read_text() == 'QY native ARM64 persistence'
    else:
        if not existing:
            document = save_file(marker,b'QY native ARM64 persistence','User','Administrator',is_private=1)
            existing = document.name
            metadata.write_text(json.dumps({'file_id':existing,'file_name':document.file_name,'file_url':document.file_url}))
        frappe.db.commit()
        assert frappe.db.exists('File', existing), 'Attachment was not committed'
        assert Path(frappe.get_doc('File',existing).get_full_path()).read_text() == 'QY native ARM64 persistence'
        from frappe.utils.pdf import get_pdf
        from pypdf import PdfReader
        pdf=get_pdf('<html><body><h1>QY ARM64 report</h1><p>VisionCare acceptance 123</p></body></html>')
        assert pdf.startswith(b'%PDF-')
        Path(frappe.get_site_path('private','files','qy-arm64-report.pdf')).write_bytes(pdf)
        assert 'VisionCare' in ''.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
        job=frappe.enqueue('frappe.utils.now',queue='short',timeout=120,is_async=True)
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            job.refresh()
            if job.is_finished: break
            if job.is_failed: raise AssertionError(job.exc_info)
            time.sleep(2)
        assert job.is_finished, 'Background job timeout'
        frappe.db.commit()
    print(json.dumps({'apps':apps,'visioncare_page':'PASS','persistence':'PASS', 'mode':'after_restart_or_restore' if os.environ.get('CHECK_PERSISTENCE') else 'pdf_and_worker'}))
finally:
    frappe.destroy()
