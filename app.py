import os
import json
import base64
import asyncio
import aiohttp
import time
import uuid
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from typing import List, Dict
import logging
import fitz  # PyMuPDF

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'output'

DEFAULT_PROMPT = """你是一位内容架构专家。请分析图片中的内容，并执行：

1. **理解重构**：不要OCR式转录，而是理解逻辑关系（并列、层级、因果）
2. **结构化输出**：使用Markdown层级（#/##/###）和列表
3. **逻辑补全**：对于OCR识别的逻辑错误语句进行自动修正
4. **重点标注**：识别并标注图片中的画线、高亮、手写标注好的重点内容
5. **格式规范**：
    - 章节标题用##
    - 概念层级用### 
    - 关键点用**加粗**
    - 逻辑关系用`→`或缩进体现

输出要求：不要随意增加、删减原图片内容，尊重原图文本，直接返回Markdown文本，不要代码块包裹，不要解释性前言。"""

DEFAULT_FORMAT_EXAMPLE = """## 第一章 概念

### 1.1 定义
**关键概念**：指...

### 1.2 特点
- 特点一：...
- 特点二：...

### 1.3 关系
概念A → 概念B → 概念C"""

CONFIG_FILE = 'prompt_config.json'

def load_prompt_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'prompt': DEFAULT_PROMPT, 'format_example': DEFAULT_FORMAT_EXAMPLE}

def save_prompt_config_to_file(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def convert_pdf_to_images(pdf_path, output_dir):
    """将PDF转换为图片"""
    images = []
    pdf_doc = fitz.open(pdf_path)
    total_pages = len(pdf_doc)
    padding = len(str(total_pages))
    for page_num in range(total_pages):
        page = pdf_doc[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_name = f"page_{str(page_num + 1).zfill(padding)}.png"
        img_path = os.path.join(output_dir, img_name)
        pix.save(img_path)
        images.append(img_path)
    pdf_doc.close()
    return images


class QwenVLProcessor:
    def __init__(self, api_key: str, custom_prompt: str = None, format_example: str = None):
        self.api_key = api_key
        self.api_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.model = "qwen-vl-plus"
        self.semaphore = asyncio.Semaphore(3)
        
        if custom_prompt:
            if format_example:
                self.system_prompt = custom_prompt + "\n\n" + f"请严格按照以下格式示例输出：\n```{format_example}```"
            else:
                self.system_prompt = custom_prompt
        else:
            self.system_prompt = DEFAULT_PROMPT

    async def process_single(self, image_path: str, session: aiohttp.ClientSession) -> Dict:
        async with self.semaphore:
            image_base64 = encode_image(image_path)
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "请提取并重构这张教育学框架图的内容："},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_base64}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                "temperature": 0.3,
                "max_tokens": 3000
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            try:
                async with session.post(
                    f"{self.api_base}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as resp:
                    result = await resp.json()
                    
                    if 'choices' in result:
                        content = result['choices'][0]['message']['content']
                        tokens = result.get('usage', {}).get('total_tokens', 0)
                        return {
                            "filename": os.path.basename(image_path),
                            "status": "success",
                            "content": content,
                            "tokens": tokens
                        }
                    else:
                        error_msg = result.get('error', {}).get('message', str(result))
                        return {
                            "filename": os.path.basename(image_path),
                            "status": "error",
                            "error": error_msg
                        }
                        
            except Exception as e:
                return {
                    "filename": os.path.basename(image_path),
                    "status": "error",
                    "error": str(e)
                }

    async def batch_process(self, file_paths: List[str], job_id: str):
        output_dir = os.path.join(app.config['OUTPUT_FOLDER'], job_id)
        os.makedirs(output_dir, exist_ok=True)
        
        async with aiohttp.ClientSession() as session:
            tasks = [self.process_single(fp, session) for fp in file_paths]
            results = await asyncio.gather(*tasks)
            
            for result in results:
                if result['status'] == 'success':
                    md_file = os.path.join(output_dir, f"{Path(result['filename']).stem}.md")
                    with open(md_file, 'w', encoding='utf-8') as f:
                        f.write(f"# {result['filename']}\n\n")
                        f.write(result['content'])
            
            summary = {
                "total": len(results),
                "success": sum(1 for r in results if r['status'] == 'success'),
                "failed": [r['filename'] for r in results if r['status'] == 'error'],
                "results": results
            }
            
            with open(os.path.join(output_dir, "summary.json"), 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            
            return summary


@app.route('/api/config/prompt', methods=['GET'])
def get_prompt_config():
    config = load_prompt_config()
    return jsonify(config)


@app.route('/api/config/prompt', methods=['POST'])
def save_prompt_config_api():
    data = request.get_json()
    config = {
        'prompt': data.get('prompt', DEFAULT_PROMPT),
        'format_example': data.get('format_example', DEFAULT_FORMAT_EXAMPLE)
    }
    save_prompt_config_to_file(config)
    return jsonify({'success': True})


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/upload', methods=['POST'])
def upload_files():
    if 'files' not in request.files:
        return jsonify({'error': '没有选择文件'}), 400
    
    files = request.files.getlist('files')
    api_key = request.form.get('api_key', '').strip()
    
    if not api_key:
        return jsonify({'error': '请输入API Key'}), 400
    
    if not files or files[0].filename == '':
        return jsonify({'error': '没有选择文件'}), 400
    
    job_id = str(uuid.uuid4())
    upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], job_id)
    os.makedirs(upload_dir, exist_ok=True)
    
    saved_files = []
    
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(upload_dir, filename)
            file.save(filepath)
            
            if filename.lower().endswith('.pdf'):
                # 转换PDF为图片
                try:
                    pdf_images = convert_pdf_to_images(filepath, upload_dir)
                    saved_files.extend(pdf_images)
                except Exception as e:
                    logger.error(f"PDF转换失败: {e}")
                    return jsonify({'error': f'PDF处理失败: {str(e)}'}), 500
            else:
                saved_files.append(filepath)
    
    if not saved_files:
        return jsonify({'error': '没有有效的图片或PDF文件'}), 400
    
    return jsonify({
        'job_id': job_id,
        'file_count': len(saved_files),
        'files': [os.path.basename(f) for f in saved_files]
    })


@app.route('/api/process', methods=['POST'])
def process_files():
    data = request.get_json()
    job_id = data.get('job_id')
    api_key = data.get('api_key', '').strip()
    custom_prompt = data.get('custom_prompt')
    format_example = data.get('format_example')
    use_custom = data.get('use_custom', False)
    
    if not job_id or not api_key:
        return jsonify({'error': '缺少必要参数'}), 400
    
    upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], job_id)
    
    if not os.path.exists(upload_dir):
        return jsonify({'error': '任务不存在'}), 404
    
    image_files = []
    for ext in ['*.png', '*.jpg', '*.jpeg']:
        image_files.extend(Path(upload_dir).glob(ext))
    
    if not image_files:
        return jsonify({'error': '没有待处理的文件'}), 400
    
    file_paths = [str(f) for f in image_files]
    
    if use_custom and custom_prompt:
        processor = QwenVLProcessor(api_key, custom_prompt, format_example)
    else:
        processor = QwenVLProcessor(api_key)
    summary = asyncio.run(processor.batch_process(file_paths, job_id))
    
    return jsonify({
        'job_id': job_id,
        'summary': summary
    })


@app.route('/api/result/<job_id>')
def get_result(job_id):
    output_dir = os.path.join(app.config['OUTPUT_FOLDER'], job_id)
    summary_file = os.path.join(output_dir, "summary.json")
    
    if not os.path.exists(summary_file):
        return jsonify({'error': '结果不存在'}), 404
    
    with open(summary_file, 'r', encoding='utf-8') as f:
        summary = json.load(f)
    
    return jsonify(summary)


@app.route('/api/download/<job_id>/<filename>')
def download_file(job_id, filename):
    output_dir = os.path.join(app.config['OUTPUT_FOLDER'], job_id)
    filepath = os.path.join(output_dir, filename)
    
    if not os.path.exists(filepath):
        return jsonify({'error': '文件不存在'}), 404
    
    return send_file(filepath, as_attachment=True)


@app.route('/api/download-all/<job_id>')
def download_all(job_id):
    import zipfile
    from io import BytesIO
    
    output_dir = os.path.join(app.config['OUTPUT_FOLDER'], job_id)
    
    if not os.path.exists(output_dir):
        return jsonify({'error': '结果不存在'}), 404
    
    memory = BytesIO()
    
    with zipfile.ZipFile(memory, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(output_dir):
            for file in files:
                if file != 'summary.json':
                    filepath = os.path.join(root, file)
                    arcname = os.path.relpath(filepath, output_dir)
                    zf.write(filepath, arcname)
    
    memory.seek(0)
    
    return send_file(
        memory,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'results_{job_id[:8]}.zip'
    )


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
