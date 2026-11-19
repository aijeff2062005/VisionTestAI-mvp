"""Run inside backend. Uses only synthetic acceptance data on the isolated site."""
import os, json, time, io
from pathlib import Path
import frappe
frappe.init(site=os.environ['QY_SITE'])
frappe.connect()
try:
    apps = frappe.get_installed_apps()
    assert set(apps) == {'frappe','erpnext','healthcare','solvronix_desk','smart_hospital','qy_vision_hospital'}, apps
    assert frappe.db.exists('Page','visioncare')
    from frappe.utils.file_manager import save_file
    marker = 'qy-release-acceptance.txt'
    existing = frappe.db.get_value('File', {'file_name':marker}, 'name')
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
        if not existing: save_file(marker,b'QY native ARM64 persistence',None,None,is_private=1)
        frappe.db.commit()
        from frappe.utils.pdf import get_pdf
        from pypdf import PdfReader
        pdf=get_pdf('<html><body><h1>QY ARM64 report</h1><p>VisionCare acceptance 123</p></body></html>')
        assert pdf.startswith(b'%PDF-')
        assert 'VisionCare' in ''.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
        job=frappe.enqueue('frappe.utils.now',queue='short',timeout=120,is_async=True)
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            job.refresh()
            if job.is_finished: break
            if job.is_failed: raise AssertionError(job.exc_info)
            time.sleep(2)
        assert job.is_finished, 'Background job timeout'
    print(json.dumps({'apps':apps,'visioncare_page':'PASS','persistence':'PASS', 'mode':'after_restart_or_restore' if os.environ.get('CHECK_PERSISTENCE') else 'pdf_and_worker'}))
finally:
    frappe.destroy()
