FROM python:3.11-slim

# 安装系统依赖（Playwright headless 运行库）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libx11-xcb1 \
    libxcomposite1 libxdamage1 libxrandr2 libgbm-dev libasound2 wget \
    && rm -rf /var/lib/apt/lists/*
   # 删除任何COPY browser_use相关指令
   # 修改pip安装命令确保安装browser_use

WORKDIR /usr/src/app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Playwright 浏览器引擎
RUN pip install playwright && playwright install chromium

# 复制测试脚本
COPY test_nav.py .

# 默认执行测试脚本
CMD ["tail", "-f", "/dev/null"]
#CMD ["python", "test_nav.py"]
