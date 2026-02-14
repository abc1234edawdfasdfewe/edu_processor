let selectedFiles = [];
let currentJobId = null;
let currentResults = [];

const API_KEY_STORAGE = 'edu_api_key';

function loadApiKey() {
    const savedKey = localStorage.getItem(API_KEY_STORAGE);
    if (savedKey) {
        document.getElementById('apiKey').value = savedKey;
        updateUploadButton();
    }
}

function saveApiKey() {
    const apiKey = document.getElementById('apiKey').value.trim();
    if (apiKey) {
        localStorage.setItem(API_KEY_STORAGE, apiKey);
    }
}

document.addEventListener('DOMContentLoaded', loadApiKey);

const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const fileList = document.getElementById('fileList');
const uploadBtn = document.getElementById('uploadBtn');
const clearBtn = document.getElementById('clearBtn');
const progressSection = document.getElementById('progressSection');
const progressBar = document.getElementById('progressBar');
const progressText = document.getElementById('progressText');
const resultSection = document.getElementById('resultSection');
const resultContent = document.getElementById('resultContent');
const downloadAllBtn = document.getElementById('downloadAllBtn');
const copyAllBtn = document.getElementById('copyAllBtn');

dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    handleFiles(e.dataTransfer.files);
});

fileInput.addEventListener('change', (e) => {
    handleFiles(e.target.files);
});

function handleFiles(files) {
    const validTypes = ['image/png', 'image/jpeg', 'image/jpg', 'application/pdf'];
    
    for (const file of files) {
        if (validTypes.includes(file.type)) {
            selectedFiles.push({
                file: file,
                name: file.name,
                size: formatFileSize(file.size),
                type: file.type
            });
        }
    }
    
    renderFileList();
    updateUploadButton();
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function renderFileList() {
    if (selectedFiles.length === 0) {
        fileList.innerHTML = '';
        return;
    }
    
    fileList.innerHTML = selectedFiles.map((item, index) => `
        <div class="file-item">
            <div class="file-info">
                <i class="bi ${getFileIcon(item.type)} file-icon"></i>
                <div>
                    <div class="file-name">${item.name}</div>
                    <div class="file-size">${item.size}</div>
                </div>
            </div>
            <i class="bi bi-x-circle btn-remove" onclick="removeFile(${index})"></i>
        </div>
    `).join('');
}

function getFileIcon(type) {
    if (type === 'application/pdf') return 'bi-file-earmark-pdf';
    return 'bi-file-earmark-image';
}

function removeFile(index) {
    selectedFiles.splice(index, 1);
    renderFileList();
    updateUploadButton();
}

function updateUploadButton() {
    const apiKey = document.getElementById('apiKey').value.trim();
    uploadBtn.disabled = selectedFiles.length === 0 || !apiKey;
}

document.getElementById('apiKey').addEventListener('input', updateUploadButton);
document.getElementById('apiKey').addEventListener('blur', saveApiKey);

clearBtn.addEventListener('click', () => {
    selectedFiles = [];
    currentJobId = null;
    renderFileList();
    updateUploadButton();
    resultSection.style.display = 'none';
    progressSection.style.display = 'none';
});

uploadBtn.addEventListener('click', async () => {
    const apiKey = document.getElementById('apiKey').value.trim();
    
    if (!apiKey) {
        alert('请输入API Key');
        return;
    }
    
    if (selectedFiles.length === 0) {
        alert('请选择文件');
        return;
    }
    
    saveApiKey();
    
    const formData = new FormData();
    selectedFiles.forEach(item => {
        formData.append('files', item.file);
    });
    formData.append('api_key', apiKey);
    
    uploadBtn.disabled = true;
    uploadBtn.innerHTML = '<span class="spinner"></span>上传中...';
    
    try {
        const uploadResponse = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        
        const uploadData = await uploadResponse.json();
        
        if (!uploadResponse.ok) {
            throw new Error(uploadData.error || '上传失败');
        }
        
        currentJobId = uploadData.job_id;
        
        progressSection.style.display = 'block';
        progressBar.style.width = '0%';
        progressBar.textContent = '0%';
        progressText.textContent = `已上传 ${uploadData.file_count} 个文件，正在处理...`;
        
        const processResponse = await fetch('/api/process', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                job_id: currentJobId,
                api_key: apiKey
            })
        });
        
        const processData = await processResponse.json();
        
        if (!processResponse.ok) {
            throw new Error(processData.error || '处理失败');
        }
        
        progressBar.style.width = '100%';
        progressBar.textContent = '100%';
        progressText.textContent = '处理完成！';
        
        await loadResults(currentJobId);
        
    } catch (error) {
        alert('错误: ' + error.message);
        progressSection.style.display = 'none';
    } finally {
        uploadBtn.disabled = false;
        uploadBtn.innerHTML = '<i class="bi bi-upload me-2"></i>上传并处理';
        updateUploadButton();
    }
});

async function loadResults(jobId) {
    try {
        const response = await fetch(`/api/result/${jobId}`);
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || '加载结果失败');
        }
        
        renderResults(data);
        resultSection.style.display = 'block';
        
        currentResults = data.results || [];
        
        downloadAllBtn.onclick = () => {
            window.location.href = `/api/download-all/${jobId}`;
        };
        
        copyAllBtn.onclick = () => {
            const combinedContent = currentResults
                .filter(r => r.status === 'success')
                .map(r => `# ${r.filename}\n\n${r.content}`)
                .join('\n\n---\n\n');
            
            if (combinedContent) {
                navigator.clipboard.writeText(combinedContent).then(() => {
                    copyAllBtn.innerHTML = '<i class="bi bi-check-lg me-1"></i>已复制';
                    setTimeout(() => {
                        copyAllBtn.innerHTML = '<i class="bi bi-clipboard me-1"></i>一键组合复制';
                    }, 2000);
                });
            }
        };
        
    } catch (error) {
        alert('加载结果失败: ' + error.message);
    }
}

function renderResults(data) {
    const results = data.results || [];
    
    if (results.length === 0) {
        resultContent.innerHTML = '<p class="text-muted">没有处理结果</p>';
        return;
    }
    
    resultContent.innerHTML = results.map(result => `
        <div class="result-card ${result.status === 'error' ? 'error' : ''} card mb-3">
            <div class="card-body">
                <div class="result-header">
                    <div class="result-title">
                        <i class="bi ${result.status === 'success' ? 'bi-check-circle-fill text-success' : 'bi-x-circle-fill text-danger'}"></i>
                        ${result.filename}
                        <span class="status-badge ${result.status}">${result.status === 'success' ? '成功' : '失败'}</span>
                    </div>
                    ${result.status === 'success' ? `
                        <button class="btn btn-sm btn-outline-primary" 
                                onclick="downloadFile('${currentJobId}', '${result.filename.replace(/\.[^.]+$/, '.md')}')">
                            <i class="bi bi-download me-1"></i>下载
                        </button>
                    ` : ''}
                </div>
                ${result.status === 'success' ? `
                    <div class="result-content">${escapeHtml(result.content)}</div>
                    <div class="mt-2 text-muted small">
                        <i class="bi bi-cpu me-1"></i>消耗Token: ${result.tokens || 0}
                    </div>
                ` : `
                    <div class="alert alert-danger mb-0">${escapeHtml(result.error)}</div>
                `}
            </div>
        </div>
    `).join('');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function downloadFile(jobId, filename) {
    window.location.href = `/api/download/${jobId}/${encodeURIComponent(filename)}`;
}
