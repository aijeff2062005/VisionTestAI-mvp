"""Small authenticated read-load characterization. No performance pass threshold."""
import concurrent.futures, http.cookiejar, json, os, platform, statistics, subprocess, time, urllib.request, urllib.parse
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Synthetic CI site only'
create = '''import frappe, os, json, secrets
frappe.init(site=os.environ['QY_SITE'], sites_path='sites'); frappe.connect(); frappe.set_user('Administrator')
users=[]
for n in range(5):
    email=f'qy-load-{n}@example.invalid'; password=secrets.token_hex(24)
    if not frappe.db.exists('User', email):
        frappe.get_doc({'doctype':'User','email':email,'first_name':f'QY Load {n}','enabled':1,'send_welcome_email':0,'roles':[{'role':'System Manager'}]}).insert(ignore_permissions=True)
    from frappe.utils.password import update_password
    update_password(email,password)
    users.append({'email':email,'password':password})
frappe.db.commit(); frappe.destroy()
print(json.dumps(users))
'''
raw=subprocess.check_output(['docker','compose','exec','-T','backend','./env/bin/python'],input=create.encode())
users=json.loads(raw.decode().splitlines()[-1])
base='http://127.0.0.1:18080'
endpoints=['qy_vision_hospital.api.patient_list.list_patients','qy_vision_hospital.api.xml_intake.list_measurement_queue']

def visit(user):
    jar=http.cookiejar.CookieJar()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(jar))
    data=urllib.parse.urlencode({'usr':user['email'],'pwd':user['password']}).encode()
    assert opener.open(urllib.request.Request(base+'/api/method/login',data=data),timeout=60).status==200
    timings=[]; errors=[]
    for _ in range(5):
        for endpoint in endpoints:
            start=time.perf_counter()
            try:
                with opener.open(base+'/api/method/'+endpoint,timeout=60) as response:
                    value=json.load(response)
                    assert response.status==200 and 'message' in value
            except Exception as error:
                errors.append(type(error).__name__)
            timings.append(time.perf_counter()-start)
    return timings,errors
trials=[]
for count in (1,3,5):
    start=time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
        results=list(pool.map(visit,users[:count]))
    times=sorted(t for ts,_ in results for t in ts);errors=[e for _,es in results for e in es]
    trials.append({'concurrent_authenticated_users':count,'requests':len(times),'errors':errors,'elapsed_seconds':time.perf_counter()-start,'median_seconds':statistics.median(times),'p95_seconds':times[max(0,int(len(times)*.95)-1)]})
images=json.loads(subprocess.check_output(['docker','image','inspect',*[os.environ[k] for k in ('CUSTOM_IMAGE','MARIADB_IMAGE','REDIS_IMAGE','MOSQUITTO_IMAGE')]],text=True))
report={'acceptance_thresholds':'UNDECIDED','environment':'GitHub hosted native ARM64, not Jetson','machine':{'architecture':platform.machine(),'kernel':platform.release(),'os':platform.platform(),'logical_cpu_count':os.cpu_count(),'memory':Path('/proc/meminfo').read_text().splitlines()[:3]},'method':'1, 3, 5 distinct synthetic System Manager accounts; each reads patient list and queue 5 times; small fresh dataset; no measurement hardware or clinical write load','trials':trials,'images':[{'tags':i['RepoTags'],'id':i['Id'],'uncompressed_bytes':i['Size']} for i in images],'max_single_image_bytes':max(i['Size'] for i in images),'archive_bytes':Path('out/qy-arm64-images.tar.gz').stat().st_size,'upload_image_max_bytes_tested':None,'upload_note':'Attachment/image upload size characterization not performed'}
Path('out/acceptance-measurements.json').write_text(json.dumps(report,indent=2))
print('Measurements recorded; no performance acceptance threshold has been applied.')
