import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("http://127.0.0.1:8550")
        await page.wait_for_timeout(3000)
        await page.screenshot(path="scratch/app_screenshot.png")
        print("Screenshot saved to scratch/app_screenshot.png")
        await browser.close()

asyncio.run(run())
