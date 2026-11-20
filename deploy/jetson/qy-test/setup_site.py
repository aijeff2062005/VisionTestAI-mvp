"""Complete the pinned Frappe/ERPNext setup workflow for a fresh isolated site."""
import json, os
from datetime import date
from pathlib import Path
import frappe
os.chdir('/home/frappe/frappe-bench/sites')
frappe.init(site=os.environ['QY_SITE'])
frappe.connect()
frappe.set_user('Administrator')
try:
    if frappe.is_setup_complete():
        print(json.dumps({'setup':'already_complete','existing_configuration':'preserved'}))
    else:
        company=os.environ.get('QY_COMPANY_NAME','QY Test Clinic')
        existing=frappe.get_all('Company',pluck='name')
        if existing and company not in existing:
            raise RuntimeError('Incomplete site has another company; configure QY_COMPANY_NAME explicitly before continuing')
        language=frappe.db.get_value('Language',os.environ.get('QY_LANGUAGE','vi'),'language_name')
        assert language, 'Unknown QY_LANGUAGE code'
        year=date.today().year
        args={
            'company_name':company,
            'company_abbr':os.environ.get('QY_COMPANY_ABBR','QYT'),
            'country':os.environ.get('QY_COUNTRY','Vietnam'),
            'currency':os.environ.get('QY_CURRENCY','VND'),
            'timezone':os.environ.get('QY_TIME_ZONE','Asia/Ho_Chi_Minh'),
            'language':language,'lang':language,
            'chart_of_accounts':'Standard',
            'fy_start_date':f'{year}-01-01','fy_end_date':f'{year}-12-31',
            'enable_telemetry':0,
        }
        from frappe.desk.page.setup_wizard.setup_wizard import setup_complete
        result=setup_complete(args)
        frappe.db.commit()
        assert result.get('status')=='ok' and frappe.is_setup_complete(),result
        frappe.clear_cache()
        print(json.dumps({'setup':'complete','company':company,'timezone':args['timezone']}))
finally:
    frappe.destroy()
