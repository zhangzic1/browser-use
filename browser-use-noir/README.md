# Playwright 浏览器自动化项目

本项目使用轻量级Docker镜像和Playwright在CentOS服务器上运行浏览器自动化任务。

## 部署步骤

1. 确保CentOS服务器已安装Docker和Docker Compose
   ```bash
   # 安装Docker
   sudo yum install -y yum-utils
   sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
   sudo yum install docker-ce docker-ce-cli containerd.io
   sudo systemctl start docker
   sudo systemctl enable docker
   
   # 安装Docker Compose
   sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.6/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
   sudo chmod +x /usr/local/bin/docker-compose
   ```

2. 克隆项目到服务器（或者上传项目文件）

3. 在项目目录中构建并启动容器：
   ```bash
   docker-compose up -d --build
   ```

4. 查看容器日志：
   ```bash
   docker-compose logs -f
   ```

## 文件说明

- `browser.py`: 主程序文件，使用Playwright进行浏览器自动化
- `docker-compose.yml`: Docker Compose配置文件
- `Dockerfile`: 轻量级Docker镜像构建文件
- `requirements.txt`: Python依赖项列表

## 注意事项

- 我们使用轻量级Python镜像，只安装Chromium浏览器而不是全部浏览器
- 镜像大小比官方Playwright镜像小很多，但仍能满足基本需求
- 项目默认只安装Chromium浏览器，如需使用Firefox或WebKit，请修改Dockerfile
- 请确保服务器有足够的内存和存储空间运行浏览器
- 如需修改代码，直接编辑`browser.py`文件后重新构建容器：`docker-compose build && docker-compose up -d` 