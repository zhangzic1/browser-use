from langchain_openai import ChatOpenAI
from browser_use import Controller, ActionResult, Browser, BrowserConfig, BrowserContextConfig
from dotenv import load_dotenv
load_dotenv()

import asyncio
import os
import json

OPENROUTER_API_KEY = "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"

llm = ChatOpenAI(
    model="anthropic/claude-3.7-sonnet",  # 可以选择任何OpenRouter支持的模型
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=0.7,
    max_tokens=2048,
    streaming=True,  # 启用流式输出
)

# 创建控制器实例
controller = Controller()

# 定义自定义操作：设置入住和退房日期
@controller.action('Set check-in and check-out dates')
async def set_dates(browser: Browser) -> ActionResult:
    # 获取当前页面的 Playwright Page 对象
    page = await browser.get_current_page()
    
    # 方法一：用 page.fill 直接设置 value（会触发 input 事件）
    await page.fill(
        'input.focus-input.show-hightlight.in-time, input[class*="in-time"]',
        '2025-06-01'
    )
    await page.fill(
        'input.focus-input.show-hightlight.out-time, input[class*="out-time"]',
        '2025-06-03'
    )
    
    # 方法二：用 page.evaluate 注入任意 JS
    await page.evaluate("""
        () => {
            const checkIn = document.querySelectorAll(
                'input.focus-input.show-hightlight.in-time, input[class*="in-time"]'
            );
            const checkOut = document.querySelectorAll(
                'input.focus-input.show-hightlight.out-time, input[class*="out-time"]'
            );
            checkIn.forEach(i => i.value = '2025-06-01');
            checkOut.forEach(i => i.value = '2025-06-03');
        }
    """)
    
    return ActionResult(extracted_content="Dates set successfully")

async def main():
    # 创建上下文配置
    context_config = BrowserContextConfig(
        cookies_file="ztrip-cookie.json"  # 使用 cookies 文件
    )
    
    # 基本浏览器配置
    config = BrowserConfig(
        headless=False,
        disable_security=True
    )

    browser = Browser(config=config)
    
    # 创建新的浏览器上下文并加载 cookies
    browser_context = await browser.new_context(context_config)
    
    with open("prompt.txt", "r", encoding="utf-8") as f:
       task_prompt = f.read()
    
    # 使用控制器代替 Agent 来处理任务
    result = await controller.run(
        task=task_prompt,
        llm=llm,
        browser_context=browser_context
    )
    print(result)

asyncio.run(main())