import asyncio
from browser_use import Browser, BrowserConfig

async def main():
    browser = Browser(config=BrowserConfig(headless=True))
    page = await browser.new_page()
    await page.goto("https://podwise.com")
    print("TITLE =", await page.title())
    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())