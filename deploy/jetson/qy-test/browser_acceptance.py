"""Authenticated browser rendering check, using only the isolated CI site."""
import os
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    response=page.request.post('http://127.0.0.1:18080/api/method/login', form={'usr':'Administrator','pwd':os.environ['FRAPPE_ADMIN_PASSWORD']})
    assert response.ok, response.status
    page.goto('http://127.0.0.1:18080/desk/visioncare',wait_until='networkidle',timeout=120000)
    page.get_by_text('Tổng quan phòng khám',exact=True).wait_for(timeout=60000)
    page.screenshot(path='out/visioncare-native-arm64.png',full_page=True)
    browser.close()
