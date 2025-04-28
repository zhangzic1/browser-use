from langchain_openai import ChatOpenAI
from browser_use import Agent, Controller
from browser_use import BrowserConfig, Browser
from dotenv import load_dotenv
load_dotenv()
from pathlib import Path
import os

import asyncio

OPENROUTER_API_KEY =

##task = "请搜索yc最新的batch，然后把前10公司名字和一句话介绍全部给我列出来，输出到txt文件"
task = "帮我搜索reddit上，youtube频道的基本的内容，将文本内容写入到同目录下的txt文件中"

# Basic configuration
config = BrowserConfig(
    headless=True,
    disable_security=True
)

browser = Browser(config=config)


llm = ChatOpenAI(
    model="anthropic/claude-3.7-sonnet",  # 可以选择任何OpenRouter支持的模型
    openai_api_key=OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
)
CURRENT_DIR = Path(__file__).parent

async def main():
    # 创建一个产品图片识别和搜索的任务描述 - 2024-03-20添加

    
    # 创建一个自定义控制器 - 2024-03-24添加
    controller = Controller()
    
    # 注册一个写入文件的自定义动作 - 2024-03-24添加
    @controller.action("将文本内容写入到同目录下的txt文件中")
    async def write_to_file(content: str, filename: str = "output.txt"):
        """
        将内容写入到指定文件中
        
        参数:
        - content: 要写入的文本内容
        - filename: 文件名，默认为output.txt
        """
        filepath = CURRENT_DIR / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"success": True, "filepath": str(filepath)}
    
    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
        controller=controller,  # 使用自定义控制器 - 2024-03-24添加
    )
    result = await agent.run()
    print(result)
    
    # 如果结果没有自动写入文件，手动将结果写入文件 - 2024-03-24添加
    if result and not os.path.exists(CURRENT_DIR / "output.txt"):
        output_filename = "reddit1.txt"
        await write_to_file(str(result), output_filename)
        print(f"结果已保存到文件: {CURRENT_DIR / output_filename}")

try:
       asyncio.run(main())
except Exception as e:
    print(f"运行出错: {e}")
    # 记录详细错误
    import traceback
    print(traceback.format_exc())