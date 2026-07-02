/**
 * PDF 压缩工具 v2.0 - 前端交互逻辑
 * 支持多文件批量上传、实时进度轮询、批量下载
 */

const state = {
    files: [],           // [{name, size, file}]
    batchId: null,
    pollingTimer: null,
};

// ─── DOM 引用 ──────────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);

const dropzone = $('#dropzone');
const fileInput = $('#file-input');
const browseBtn = $('#browse-btn');
const fileList = $('#file-list');
const fileListItems = $('#file-list-items');
const fileCount = $('#file-count');
const clearAllBtn = $('#clear-all-btn');
const compressLevels = $('#compress-levels');
const compressBtn = $('#compress-btn');
const uploadSection = $('#upload-section');
const processingSection = $('#processing-section');
const processingTitle = $('#processing-title');
const processingProgress = $('#processing-progress');
const processingList = $('#processing-list');
const processingActions = $('#processing-actions');
const downloadAllBtn = $('#download-all-btn');
const resetBtn = $('#reset-btn');
const errorSection = $('#error-section');
const errorMessage = $('#error-message');
const errorResetBtn = $('#error-reset-btn');

// ─── 工具函数 ──────────────────────────────────────────────────
function formatSize(bytes) {
    if (bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function show(el) { el.style.display = ''; }
function hide(el) { el.style.display = 'none'; }

function showSection(section) {
    hide(uploadSection);
    hide(processingSection);
    hide(errorSection);
    show(section);
}

// ─── 文件选择与列表管理 ────────────────────────────────────────
function addFiles(newFiles) {
    let added = 0;
    for (const file of newFiles) {
        if (!file.name.toLowerCase().endsWith('.pdf')) continue;
        // 避免重复（按 name + size 判断）
        if (state.files.some(f => f.name === file.name && f.size === file.size)) continue;
        state.files.push({ name: file.name, size: file.size, file });
        added++;
    }
    if (added > 0) renderFileList();
}

function removeFile(index) {
    state.files.splice(index, 1);
    renderFileList();
}

function clearFiles() {
    state.files = [];
    fileInput.value = '';
    renderFileList();
}

function renderFileList() {
    if (state.files.length === 0) {
        hide(fileList);
        hide(compressLevels);
        compressBtn.disabled = true;
        compressBtn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M3 6l6-4 6 4M9 2v10" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M3 12v3h12v-3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            压缩文件
        `;
        return;
    }

    show(fileList);
    show(compressLevels);
    compressBtn.disabled = false;

    fileCount.textContent = `已选择 ${state.files.length} 个文件`;
    compressBtn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M3 6l6-4 6 4M9 2v10" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M3 12v3h12v-3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        压缩 ${state.files.length} 个文件
    `;

    fileListItems.innerHTML = state.files.map((f, i) => `
        <div class="file-item">
            <div class="file-item-icon">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <rect x="2" y="1" width="16" height="18" rx="2" stroke="currentColor" stroke-width="1.5"/>
                    <path d="M6 9h8M6 12h6M6 6h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
            </div>
            <div class="file-item-info">
                <span class="file-item-name">${escapeHtml(f.name)}</span>
                <span class="file-item-size">${formatSize(f.size)}</span>
            </div>
            <button class="file-item-remove" data-index="${i}" title="移除文件">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                </svg>
            </button>
        </div>
    `).join('');

    // 绑定移除按钮事件
    fileListItems.querySelectorAll('.file-item-remove').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            removeFile(parseInt(btn.dataset.index));
        });
    });
}

// ─── 事件绑定 ──────────────────────────────────────────────────

// 点击浏览
browseBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    fileInput.click();
});

fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
        addFiles(Array.from(fileInput.files));
        fileInput.value = '';  // 清空以支持重复选择同一文件
    }
});

// 点击 dropzone 打开文件选择
dropzone.addEventListener('click', () => {
    fileInput.click();
});

// 拖拽事件
dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('drag-over');
});

dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('drag-over');
});

dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('drag-over');
    if (e.dataTransfer.files.length > 0) {
        addFiles(Array.from(e.dataTransfer.files));
    }
});

// 粘贴文件支持
document.addEventListener('paste', (e) => {
    // 如果焦点在 input/textarea 中，不拦截
    if (document.activeElement && ['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
        return;
    }
    const items = e.clipboardData?.items;
    if (!items) return;

    const files = [];
    for (const item of items) {
        if (item.kind === 'file') {
            const file = item.getAsFile();
            if (file && file.name.toLowerCase().endsWith('.pdf')) {
                files.push(file);
            }
        }
    }
    if (files.length > 0) {
        addFiles(files);
    }
});

// 清空全部
clearAllBtn.addEventListener('click', () => {
    clearFiles();
});

// 压缩级别切换高亮
document.querySelectorAll('input[name="level"]').forEach((radio) => {
    radio.addEventListener('change', () => {
        document.querySelectorAll('.level-option').forEach((opt) => opt.classList.remove('active'));
        radio.closest('.level-option').classList.add('active');
    });
});

// 开始压缩
compressBtn.addEventListener('click', () => {
    if (state.files.length === 0) return;
    startCompress();
});

// 重置
resetBtn.addEventListener('click', () => {
    stopPolling();
    clearFiles();
    showSection(uploadSection);
});

// 错误恢复
errorResetBtn.addEventListener('click', () => {
    clearFiles();
    showSection(uploadSection);
});

// ─── 上传 & 压缩流程 ──────────────────────────────────────────
async function startCompress() {
    if (state.files.length === 0) return;

    // 切换到处理视图
    showSection(processingSection);
    processingTitle.textContent = '正在上传...';
    processingProgress.textContent = '';
    processingList.innerHTML = `
        <div class="processing-item status-queued">
            <div class="status-icon queued">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5"/></svg>
            </div>
            <div class="processing-item-info">
                <span class="processing-item-name">准备上传 ${state.files.length} 个文件...</span>
            </div>
        </div>
    `;
    hide(processingActions);

    // 构建 FormData
    const formData = new FormData();
    for (const f of state.files) {
        formData.append('files', f.file, f.name);
    }
    const levelRadio = document.querySelector('input[name="level"]:checked');
    formData.append('level', levelRadio ? levelRadio.value : 'standard');

    try {
        const resp = await fetch('/upload', {
            method: 'POST',
            body: formData,
        });

        const data = await resp.json();

        if (!resp.ok || !data.success) {
            throw new Error(data.error || '上传失败');
        }

        state.batchId = data.batch_id;

        // 初始化进度视图：为每个文件创建占位卡片
        processingTitle.textContent = '正在压缩...';
        processingProgress.textContent = `已完成 0/${data.total}`;
        processingList.innerHTML = data.files.map(f => renderFileStatus({
            id: f.id,
            name: f.name,
            status: 'queued',
        })).join('');

        // 开始轮询
        startPolling(data.batch_id);

    } catch (err) {
        showError(err.message);
    }
}

// ─── 进度轮询 ─────────────────────────────────────────────────
function startPolling(batchId) {
    stopPolling();  // 清除旧的

    const poll = async () => {
        try {
            const resp = await fetch(`/status/${batchId}`);
            if (!resp.ok) {
                // 批次可能已过期
                stopPolling();
                showError('批次状态查询失败');
                return;
            }

            const data = await resp.json();
            renderProcessing(data);

            if (data.all_done) {
                stopPolling();
            }
        } catch (err) {
            // 网络错误时继续重试
        }
    };

    state.pollingTimer = setInterval(poll, 800);
    poll();  // 立即首次查询
}

function stopPolling() {
    if (state.pollingTimer) {
        clearInterval(state.pollingTimer);
        state.pollingTimer = null;
    }
}

// ─── 渲染处理进度 ─────────────────────────────────────────────
const STATUS_ICONS = {
    queued: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="8" stroke="currentColor" stroke-width="1.5"/><path d="M10 5v5l3 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    compressing: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="8" stroke="currentColor" stroke-width="1.5" stroke-dasharray="40" stroke-dashoffset="10"/></svg>`,
    done: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="8" stroke="currentColor" stroke-width="1.5"/><path d="M7 10l2 2 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    error: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="8" stroke="currentColor" stroke-width="1.5"/><path d="M7 7l6 6M13 7l-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`,
};

const STATUS_TEXT = {
    queued: '排队中',
    compressing: '压缩中...',
    done: '完成',
    error: '失败',
};

function renderFileStatus(f) {
    const icon = STATUS_ICONS[f.status] || STATUS_ICONS.queued;
    const text = STATUS_TEXT[f.status] || '';
    let resultHtml = '';
    let downloadHtml = '';

    if (f.status === 'done') {
        const ratioClass = f.ratio > 10 ? 'ratio-good' : 'ratio-ok';
        const engineBadge = f.engine === 'ghostscript'
            ? '<span style="font-size:10px;color:var(--green-600);background:rgba(34,197,94,0.1);padding:1px 5px;border-radius:3px;margin-left:4px;">GS</span>'
            : '';
        resultHtml = `
            <div class="processing-item-result">
                <span class="result-size">${formatSize(f.compressed_size)}</span>
                <span class="result-ratio ${ratioClass}">-${f.ratio}%${engineBadge}</span>
            </div>
        `;
        downloadHtml = `<a class="processing-item-download" href="/download/${f.id}" download>下载</a>`;
    } else if (f.status === 'error') {
        resultHtml = `
            <div class="processing-item-result">
                <span class="result-ratio" style="color:var(--red-500);max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(f.error || '')}">${escapeHtml(f.error || '未知错误')}</span>
            </div>
        `;
    }

    // 状态文本附加引擎信息
    let statusText = text;
    if (f.status === 'done' && f.engine === 'ghostscript') {
        statusText = '完成 · Ghostscript';
    }

    return `
        <div class="processing-item status-${f.status}">
            <div class="status-icon ${f.status}">${icon}</div>
            <div class="processing-item-info">
                <span class="processing-item-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>
                <span class="processing-item-status-text">${statusText}</span>
            </div>
            ${resultHtml}
            ${downloadHtml}
        </div>
    `;
}

function renderProcessing(data) {
    const { total, completed, all_done, files } = data;

    // 更新头部
    processingTitle.textContent = all_done ? '压缩完成' : '正在压缩...';
    const errorCount = files.filter(f => f.status === 'error').length;
    if (all_done) {
        processingProgress.textContent = errorCount > 0
            ? `全部完成 · ${errorCount} 个失败`
            : '全部完成';
    } else {
        processingProgress.textContent = `已完成 ${completed}/${total}`;
    }

    // 渲染文件列表
    let html = '';

    // 全部完成时，插入汇总栏
    if (all_done) {
        const doneFiles = files.filter(f => f.status === 'done');
        if (doneFiles.length > 0) {
            const totalOrig = doneFiles.reduce((s, f) => s + f.original_size, 0);
            const totalComp = doneFiles.reduce((s, f) => s + f.compressed_size, 0);
            const avgRatio = totalOrig > 0 ? Math.round((1 - totalComp / totalOrig) * 100) : 0;

            html += `
                <div class="result-summary">
                    <div class="summary-stat">
                        <span class="summary-stat-label">处理文件</span>
                        <span class="summary-stat-value">${doneFiles.length} 个</span>
                    </div>
                    <div class="summary-stat">
                        <span class="summary-stat-label">原始大小</span>
                        <span class="summary-stat-value">${formatSize(totalOrig)}</span>
                    </div>
                    <div class="summary-stat">
                        <span class="summary-stat-label">压缩后</span>
                        <span class="summary-stat-value">${formatSize(totalComp)}</span>
                    </div>
                    <div class="summary-stat">
                        <span class="summary-stat-label">压缩率</span>
                        <span class="summary-stat-value highlight">-${avgRatio}%</span>
                    </div>
                </div>
            `;
        }
    }

    html += files.map(f => renderFileStatus(f)).join('');
    processingList.innerHTML = html;

    // 全部完成时显示操作按钮
    if (all_done) {
        show(processingActions);
        const doneCount = files.filter(f => f.status === 'done').length;
        if (doneCount > 0) {
            downloadAllBtn.href = `/download-all/${data.batch_id}`;
            downloadAllBtn.style.display = '';
        } else {
            downloadAllBtn.style.display = 'none';
        }
    }
}

// ─── 错误展示 ─────────────────────────────────────────────────
function showError(msg) {
    showSection(errorSection);
    errorMessage.textContent = msg;
}
