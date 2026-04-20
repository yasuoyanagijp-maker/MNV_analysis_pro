from playwright.sync_api import sync_playwright
import time

try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("http://127.0.0.1:8550")
        page.fill("input[type='text']", "Dr. Yanagi")
        page.fill("input[type='password']", "ariake2024")
        page.click("text=Secure Login")
        time.sleep(2)
        
        # We need to fill the Manual Path.
        page.fill("input[type='text']", "/tmp/mnv_samples/Main Report1.png")
        page.keyboard.press("Enter")
        time.sleep(3)
        
        page.screenshot(path="roi_freeze.png")
        browser.close()
        print("Screenshot taken successfully")
except Exception as e:
    print(f"Error taking screenshot: {e}")
