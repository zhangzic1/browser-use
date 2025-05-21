from langchain_openai import ChatOpenAI
from browser_use import Agent, Browser, BrowserConfig, BrowserContextConfig
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
       
    agent = Agent(
        task=task_prompt,
        llm=llm,
        browser_context=browser_context  # 使用已创建的带有 cookies 的上下文
    )
    result = await agent.run()
    print(result)

asyncio.run(main())