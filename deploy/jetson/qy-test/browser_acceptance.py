"""Authenticated rendering assertion; realtime traffic must not block readiness."""
import json, os
from pathlib import Path
from playwright.sync_api import sync_playwright
report={'visioncare_visible':False,'page_errors':[]}
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    page.on('pageerror',lambda error:report['page_errors'].append(str(error)))
    try:
        response=page.request.post('http://127.0.0.1:18080/api/method/login', form={'usr':'Administrator','pwd':os.environ['FRAPPE_ADMIN_PASSWORD']})
        assert response.ok, response.status
        # Frappe polls/reconnects in the background; assert actual UI readiness
        # instead of waiting for all network traffic to stop.
        page.goto('http://127.0.0.1:18080/desk/visioncare',wait_until='domcontentloaded',timeout=60000)
        page.get_by_text('Tổng quan phòng khám',exact=True).wait_for(timeout=60000)
        assert page.evaluate('window.frappe?.session?.user')=='Administrator'
        report['visioncare_visible']=True
    finally:
        report['url']=page.url
        page.screenshot(path='out/visioncare-native-arm64.png',full_page=True)
        Path('out/acceptance-browser.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
        browser.close()
