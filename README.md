# 教育学框架图智能提取

基于 Qwen3-VL-Plus 模型的图片/PDF内容提取工具，支持批量上传并输出结构化Markdown。

## 功能特性

- 支持批量上传图片(PNG/JPG)和PDF文件
- PDF自动转换为图片处理
- 使用Qwen3-VL-Plus进行视觉理解
- 输出结构化Markdown格式
- 实时处理进度显示
- 单文件/批量下载结果

## 安装

```bash
pip install -r requirements.txt
```

## 使用方法

1. 启动服务：
```bash
python app.py
```

2. 访问 http://localhost:5000

3. 输入阿里云DashScope API Key（需开通qwen-vl-plus模型）

4. 上传图片或PDF文件，点击"上传并处理"

## API Key 获取

访问 [阿里云DashScope控制台](https://dashscope.console.aliyun.com/) 注册并获取API Key。

## 项目结构

```
edu_processor/
├── app.py              # Flask后端
├── templates/
│   └── index.html      # 前端页面
├── static/
│   ├── css/style.css   # 样式
│   └── js/app.js       # 脚本
├── uploads/            # 上传文件临时目录
├── output/            # 处理结果目录
└── requirements.txt   # 依赖
```
