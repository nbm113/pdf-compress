# PDF Compress - Code Wiki

> **版本**: v2.0  
> **技术栈**: Python + Flask + pikepdf + Ghostscript  
> **项目类型**: 本地部署的 PDF 批量压缩 Web 服务

---

## 目录

1. [项目概述](#1-项目概述)
2. [整体架构](#2-整体架构)
3. [目录结构](#3-目录结构)
4. [后端模块详解](#4-后端模块详解)
5. [前端模块详解](#5-前端模块详解)
6. [核心压缩引擎](#6-核心压缩引擎)
7. [API 接口](#7-api-接口)
8. [依赖关系](#8-依赖关系)
9. [部署与运行](#9-部署与运行)
10. [构建打包](#10-构建打包)

---

## 1. 项目概述

### 1.1 项目简介

PDF Compress 是一个**纯本地部署**的 PDF 批量压缩工具，基于 Flask Web 框架构建，提供友好的浏览器交互界面。所有文件处理均在本地完成，不上传任何外部服务器，保证数据安全。

### 1.2 核心特性

- **多文件批量压缩**: 支持一次上传多个 PDF 文件并发处理
- **三级压缩强度**: 轻量 / 标准 / 极致，适应不同场景
- **双压缩引擎**: Ghostscript（工业级，效果最佳）+ pikepdf（轻量回退）
- **实时进度反馈**: 前端轮询 + 逐文件状态展示
- **并发控制**: Semaphore 限制同时压缩数量（默认 2 个）
- **自动清理**: 30 分钟后自动清理临时文件和批次状态
- **跨平台**: Windows / macOS / Linux 均可运行
- **一键打包**: 支持 PyInstaller 打包为 Windows 自包含 exe

### 1.3 技术选型

| 层级 | 技术 | 用途 |
|------|------|------|
| Web 框架 | Flask 3.0+ | HTTP 服务与路由 |
| PDF 处理主引擎 | Ghostscript | 工业级 PDF 重渲染压缩 |
| PDF 处理回退引擎 | pikepdf 9.0+ | 纯 Python PDF 流操作 |
| 图像处理 | Pillow 10.0+ | 图片降采样、格式转换 |
| 前端 | 原生 HTML/CSS/JS | 无需构建工具，轻量交互 |
| 并发模型 | 线程 + Semaphore | 批次内多文件并发 |
| 打包 | PyInstaller | Windows 单文件夹分发 |

---

## 2. 整体架构

### 2.1 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        用户浏览器                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  文件上传     │  │  进度轮询     │  │  结果下载         │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
└─────────┼─────────────────┼─────────────────────┼────────────┘
          │                 │                     │
          ▼                 ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                      Flask Web Server (端口 5050)            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │  /       │  │ /upload  │  │ /status  │  │ /download  │  │
│  │  首页    │  │  上传    │  │  进度    │  │  下载      │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └─────┬──────┘  │
└───────┼──────────────┼─────────────┼───────────────┼─────────┘
        │              │             │               │
        └──────────────┴──────┬──────┴───────────────┘
                               │
                    ┌──────────▼──────────┐
                    │   批次处理线程池      │
                    │  (Semaphore 控制)    │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   智能压缩引擎调度    │
                    │  Ghostscript → pikepdf│
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   文件系统 (uploads) │
                    │  输入/输出临时文件   │
                    └─────────────────────┘
```

### 2.2 核心数据流

1. **上传阶段**: 用户选择 PDF → 前端构造 FormData → POST `/upload` → 服务端保存文件到 `uploads/` → 注册批次 → 启动后台处理线程
2. **压缩阶段**: 批次线程为每个文件启动子线程 → Semaphore 限制并发 → 调用压缩引擎 → 更新批次状态
3. **进度阶段**: 前端每 800ms 轮询 `/status/<batch_id>` → 渲染各文件状态
4. **下载阶段**: 单文件 GET `/download/<file_id>` / 批量 GET `/download-all/<batch_id>`（打包 ZIP）

---

## 3. 目录结构

```
PDF Compress/
├── app.py                    # 主应用：Flask 服务 + 压缩核心逻辑
├── requirements.txt          # Python 依赖清单
├── run.bat                   # Windows 一键启动脚本
├── start.sh                  # macOS/Linux 一键启动脚本
├── build_exe.bat             # Windows PyInstaller 打包脚本
│
├── templates/
│   └── index.html            # 单页应用 HTML 模板
│
├── static/
│   ├── css/
│   │   └── style.css         # 全部样式（响应式设计）
│   └── js/
│       └── app.js            # 前端交互逻辑
│
├── uploads/                  # 运行时生成：临时文件存储
│
├── .github/
│   └── workflows/
│       └── build-windows.yml # GitHub Actions CI 构建
│
├── .gitignore                # Git 忽略规则
└── 分单.PDF                   # 测试用 PDF 文件
```

---

## 4. 后端模块详解

后端所有逻辑集中在 [app.py](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/app.py) 中，按功能划分为以下模块：

### 4.1 路径配置与 Flask 初始化

**位置**: [app.py#L22-L40](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/app.py#L22-L40)

```python
# 兼容 PyInstaller 打包
if getattr(sys, 'frozen', False):
    BUNDLE_DIR = sys._MEIPASS      # 打包资源目录（只读）
    DATA_DIR = os.path.dirname(sys.executable)  # 数据目录（可写）
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = BUNDLE_DIR
```

**关键配置**:
- `MAX_CONTENT_LENGTH`: 500MB 总上传限制
- `UPLOAD_FOLDER`: 上传文件存储目录（自动创建）
- 模板目录和静态目录根据运行模式动态指向

### 4.2 并发控制模块

**位置**: [app.py#L42-L48](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/app.py#L42-L48)

| 变量 | 类型 | 作用 |
|------|------|------|
| `MAX_CONCURRENT` | int | 最大并发压缩数，默认 2 |
| `compress_semaphore` | `threading.Semaphore` | 控制同时进行的压缩任务数 |
| `batch_state` | dict | 批次状态内存存储（batch_id → 状态对象） |
| `batch_lock` | `threading.Lock` | 保护 `batch_state` 的线程锁 |

**批次状态结构**:
```python
{
    'files': [...],        # 文件信息列表
    'level': 'standard',   # 压缩级别
    'total': 5,            # 总文件数
    'completed': 2,        # 已完成数
    'all_done': False,     # 是否全部完成
    'created_at': 12345.0  # 创建时间戳
}
```

### 4.3 定时清理模块

**函数**: `cleanup_old_files()`  
**位置**: [app.py#L52-L68](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/app.py#L52-L68)

- 清理 `uploads/` 目录下超过 30 分钟（1800秒）的文件
- 清理过期的批次状态记录
- 在每次首页访问和上传时自动触发
- 防止磁盘空间泄漏

### 4.4 Ghostscript 检测模块

**位置**: [app.py#L71-L111](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/app.py#L71-L111)

#### 核心函数

**`_detect_ghostscript()`** — 检测系统中可用的 Ghostscript

检测优先级：
1. **PyInstaller 内嵌**: `_MEIPASS/gs/` 目录下的 `gswin64c.exe` / `gswin32c.exe` / `gs`
2. **系统 PATH**: 通过 `shutil.which()` 查找 `gs` / `gswin64c` / `gswin32c`
3. **Windows 常见安装位置**: `C:\Program Files\gs\gs<version>\bin\`（版本 10.07.1 ~ 10.05.0）

检测结果缓存于全局变量 `_GS_EXECUTABLE` 和 `_GS_CHECKED`，避免重复检测。

**`has_ghostscript()`** — 对外暴露的检测接口，返回布尔值。

### 4.5 批次处理模块

**函数**: `process_batch(batch_id)`  
**位置**: [app.py#L338-L384](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/app.py#L338-L384)

**工作流程**:
1. 从 `batch_state` 获取批次信息（加锁读取）
2. 为每个文件启动一个后台线程
3. 每个线程通过 `compress_semaphore` 获取并发槽位
4. 调用 `compress_pdf()` 执行压缩
5. 成功/失败均更新批次状态（加锁写入）
6. 所有线程完成后标记 `all_done = True`

**文件状态流转**:
```
queued → compressing → done
                  ↘ error
```

### 4.6 路由模块

详见 [第 7 章 API 接口](#7-api-接口)。

---

## 5. 前端模块详解

前端是一个**无框架**的单页应用，由 HTML 模板 + CSS 样式 + 原生 JS 组成。

### 5.1 HTML 结构

**文件**: [templates/index.html](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/templates/index.html)

页面分为三个主要 section（同一时间只显示一个）：

| Section | ID | 用途 |
|---------|----|------|
| 上传区 | `#upload-section` | 文件拖拽/选择 + 压缩级别选择 |
| 处理区 | `#processing-section` | 实时进度 + 结果列表 + 下载按钮 |
| 错误区 | `#error-section` | 错误信息展示 + 重试 |

### 5.2 CSS 样式

**文件**: [static/css/style.css](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/static/css/style.css)

**设计系统**:
- CSS 变量定义的颜色体系（灰/蓝/绿/红四色）
- 圆角 8px / 12px 两档
- 阴影分 `--shadow` 和 `--shadow-md` 两档
- 响应式设计：`@media (max-width: 480px)` 移动端适配

**主要样式模块**:
- `.dropzone` — 拖拽上传区（含 hover/drag-over 状态）
- `.file-item` — 文件列表项
- `.level-card` — 压缩级别选项卡
- `.processing-item` — 进度项（四种状态：queued/compressing/done/error）
- `.result-summary` — 完成后的汇总栏
- `.btn-primary` / `.btn-secondary` — 按钮组件

### 5.3 JavaScript 逻辑

**文件**: [static/js/app.js](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/static/js/app.js)

#### 状态管理

全局 `state` 对象：
```javascript
const state = {
    files: [],        // 待上传文件列表 [{name, size, file}]
    batchId: null,    // 当前批次 ID
    pollingTimer: null // 轮询定时器
};
```

#### 核心函数

| 函数 | 位置 | 作用 |
|------|------|------|
| `addFiles(newFiles)` | [app.js#L61-L71](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/static/js/app.js#L61-L71) | 添加文件（去重） |
| `removeFile(index)` | [app.js#L73-L76](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/static/js/app.js#L73-L76) | 移除指定文件 |
| `renderFileList()` | [app.js#L84-L139](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/static/js/app.js#L84-L139) | 渲染文件列表 |
| `startCompress()` | [app.js#L235-L291](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/static/js/app.js#L235-L291) | 上传并开始压缩 |
| `startPolling(batchId)` | [app.js#L294-L320](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/static/js/app.js#L294-L320) | 启动进度轮询（800ms 间隔） |
| `renderProcessing(data)` | [app.js#L389-L451](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/static/js/app.js#L389-L451) | 渲染处理进度和结果 |
| `renderFileStatus(f)` | [app.js#L344-L387](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/static/js/app.js#L344-L387) | 渲染单个文件状态卡片 |
| `formatSize(bytes)` | [app.js#L37-L42](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/static/js/app.js#L37-L42) | 字节数格式化 |
| `escapeHtml(str)` | [app.js#L44-L48](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/static/js/app.js#L44-L48) | HTML 转义（防 XSS） |

#### 交互特性

- **拖拽上传**: `dragover` / `dragleave` / `drop` 事件处理
- **粘贴上传**: 监听 `document.paste`，从剪贴板获取文件
- **重复选择**: 支持多次拖拽/浏览追加文件（自动去重）
- **键盘快捷键**: 粘贴支持（非输入框焦点时）

---

## 6. 核心压缩引擎

### 6.1 智能调度策略

**函数**: `compress_pdf(input_path, output_path, level)`  
**位置**: [app.py#L171-L197](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/app.py#L171-L197)

压缩策略决策树：

```
compress_pdf(level)
    │
    ├─ level == 'light'
    │   └─ → 直接使用 pikepdf（仅结构优化）
    │
    └─ level in ('standard', 'extreme')
        ├─ 有 Ghostscript ?
        │   ├─ 是 → 尝试 Ghostscript 压缩
        │   │   ├─ 压缩后 < 原大小 ?
        │   │   │   └─ 是 → 返回 GS 结果
        │   │   └─ 否（甚至变大） → 回退 pikepdf
        │   └─ 否 → 直接使用 pikepdf
        └─ GS 抛异常 → 回退 pikepdf
```

### 6.2 Ghostscript 压缩引擎

**函数**: `compress_with_ghostscript(input_path, output_path, level)`  
**位置**: [app.py#L114-L167](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/app.py#L114-L167)

#### 级别映射

| 压缩级别 | Ghostscript PDFSETTINGS | DPI | 说明 |
|----------|------------------------|-----|------|
| `standard` | `/printer` | 300 | 近乎无损，高清 |
| `extreme` | `/ebook` | 150 | 文字清晰 + 图片压缩 + 字体子集化 |

> **注意**: `/screen` (72dpi) 未使用，因为文字模糊体验差。

#### 关键参数

```python
cmd = [
    '-sDEVICE=pdfwrite',        # 输出 PDF
    '-dCompatibilityLevel=1.5', # PDF 1.5 兼容性
    '-dPDFSETTINGS=...',        # 预设配置
    '-dNOPAUSE -dQUIET -dBATCH',# 静默批处理
    '-dEmbedAllFonts=false',    # 不嵌入原文件未嵌入的字体（防膨胀）
    '-dCompressFonts=true',     # 压缩字体
    '-dSubsetFonts=true',       # 字体子集化（只嵌入用到的字形）
    '-dOptimize=true',          # 优化结构
    '-dDetectDuplicateImages=true', # 去重图片
    '-dPreserveHalftoneInfo=false', # 不保留半色调信息
]
```

#### 异常处理

| 异常类型 | 处理方式 |
|----------|----------|
| `TimeoutExpired` (>5分钟) | 抛出运行时异常，建议轻量压缩 |
| `CalledProcessError` | PDF 可能已损坏 |
| `FileNotFoundError` | 未找到 Ghostscript |

### 6.3 pikepdf 压缩引擎（回退）

**函数**: `_compress_pdf_pikepdf(input_path, output_path, level)`  
**位置**: [app.py#L200-L265](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/app.py#L200-L265)

#### 三级配置

| 配置项 | light | standard | extreme |
|--------|-------|----------|---------|
| `max_dim`（最长边像素） | None | 2000 | 1200 |
| `jpeg_quality`（JPEG 质量） | None | 85 | 55 |
| `convert_to_jpeg`（格式转换） | ❌ | ✅ | ✅ |
| `strip_metadata`（清除元数据） | ✅ | ✅ | ✅ |
| `remove_unreferenced`（移除未引用资源） | ✅ | ✅ | ✅ |
| `recompress_flate`（重新压缩流） | ❌ | ✅ | ✅ |

#### 处理步骤

1. **图片处理**: 遍历所有页面的图片，调用 `_process_page_images()`
2. **元数据清除**: 清空 PDF 元数据（作者、创建时间等）
3. **资源清理**: `pdf.remove_unreferenced_resources()`
4. **保存优化**: `linearize=True`（快速 Web 查看）+ 对象流压缩

### 6.4 图片处理核心

**函数**: `_process_page_images(page, PILImage, io_module, cfg)`  
**位置**: [app.py#L268-L334](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/app.py#L268-L334)

**图片处理三步曲**：

```
原始图片流
    │
    ├─ 1. 降采样（最长边 > max_dim 时）
    │     等比缩小到 max_dim（LANCZOS 高质量算法）
    │
    ├─ 2. 色彩空间转换
    │     RGBA → RGB（白底合成）
    │     CMYK / P / PA / LA → RGB
    │     其他 → RGB
    │
    ├─ 3. JPEG 重新编码
    │     指定 quality + optimize=True
    │
    └─ 4. 体积判断
          JPEG < 原图 ? → 替换图片流
          JPEG ≥ 原图 ? → 保留原图（不做无用功）
```

**替换后的图片流属性**:
- `Filter`: `/DCTDecode`（JPEG 编码）
- `ColorSpace`: `/DeviceRGB` 或 `/DeviceGray`
- `Width` / `Height`: 新尺寸
- `BitsPerComponent`: 8

---

## 7. API 接口

### 7.1 接口总览

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/` | 首页渲染 |
| POST | `/upload` | 上传文件并开始压缩 |
| GET | `/status/<batch_id>` | 查询批次进度 |
| GET | `/download/<file_id>` | 下载单个压缩文件 |
| GET | `/download-all/<batch_id>` | 批量下载（ZIP 打包） |

### 7.2 GET `/` — 首页

**响应**: 渲染 HTML 页面，模板变量 `has_ghostscript` 指示是否启用 Ghostscript。

**副作用**: 触发一次 `cleanup_old_files()`

### 7.3 POST `/upload` — 上传并开始压缩

**请求**:
- Content-Type: `multipart/form-data`
- 字段:
  - `files`: 多个 PDF 文件
  - `level`: 压缩级别（`light` / `standard` / `extreme`），默认 `standard`

**成功响应** (200):
```json
{
    "success": true,
    "batch_id": "a1b2c3d4e5f6",
    "total": 3,
    "files": [
        {"id": "xxx", "name": "file1.pdf"},
        {"id": "yyy", "name": "file2.pdf"}
    ]
}
```

**失败响应** (400/500):
```json
{
    "success": false,
    "error": "错误信息"
}
```

**实现位置**: [app.py#L395-L457](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/app.py#L395-L457)

### 7.4 GET `/status/<batch_id>` — 查询进度

**路径参数**: `batch_id` — 批次 ID

**成功响应** (200):
```json
{
    "batch_id": "a1b2c3d4e5f6",
    "total": 3,
    "completed": 2,
    "all_done": false,
    "level": "standard",
    "files": [
        {
            "id": "xxx",
            "name": "file1.pdf",
            "status": "done",
            "original_size": 1024000,
            "compressed_size": 512000,
            "ratio": 50.0,
            "error": null,
            "engine": "ghostscript"
        },
        {
            "id": "yyy",
            "name": "file2.pdf",
            "status": "compressing",
            ...
        },
        {
            "id": "zzz",
            "name": "file3.pdf",
            "status": "queued",
            ...
        }
    ]
}
```

**文件状态枚举**: `queued` | `compressing` | `done` | `error`

**失败响应** (404):
```json
{"error": "批次不存在或已过期"}
```

**实现位置**: [app.py#L460-L487](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/app.py#L460-L487)

### 7.5 GET `/download/<file_id>` — 下载单个文件

**路径参数**: `file_id` — 文件 ID

**成功响应**: 文件流，Content-Disposition: attachment，文件名 `compressed_{id}.pdf`

**失败响应** (404):
```json
{"success": false, "error": "文件已过期，请重新上传"}
```

**实现位置**: [app.py#L490-L504](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/app.py#L490-L504)

### 7.6 GET `/download-all/<batch_id>` — 批量下载

**路径参数**: `batch_id` — 批次 ID

**功能**: 将所有成功压缩的文件打包为 ZIP 下载，文件名自动加 `_compressed` 后缀。

**成功响应**: ZIP 文件流，文件名 `compressed_batch_{batch_id}.zip`

**失败响应** (404):
```json
{"error": "批次不存在或已过期"}
// 或
{"error": "没有可下载的文件"}
```

**实现位置**: [app.py#L507-L537](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/app.py#L507-L537)

---

## 8. 依赖关系

### 8.1 Python 依赖

**文件**: [requirements.txt](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/requirements.txt)

| 依赖 | 最低版本 | 用途 | 必需 |
|------|----------|------|------|
| Flask | 3.0.0 | Web 框架 | ✅ |
| pikepdf | 9.0.0 | PDF 操作（回退引擎） | ✅ |
| Pillow | 10.0.0 | 图片处理 | ✅（pikepdf 模式下图片压缩需要） |

### 8.2 可选外部依赖

| 依赖 | 用途 | 安装方式 |
|------|------|----------|
| Ghostscript | 工业级 PDF 压缩引擎（推荐） | Windows: [官网下载](https://ghostscript.com/releases/gsdnld.html)<br>macOS: `brew install ghostscript`<br>Linux: `apt install ghostscript` |

### 8.3 开发/打包依赖

| 依赖 | 用途 |
|------|------|
| PyInstaller | 打包为 Windows 可执行文件 |
| GitHub Actions | CI 自动构建 |

### 8.4 内部依赖关系图

```
app.py (主模块)
  ├── Flask (Web 框架)
  │   ├── render_template → templates/index.html
  │   ├── static_folder  → static/css/style.css
  │   └── static_folder  → static/js/app.js
  │
  ├── 压缩核心
  │   ├── Ghostscript (可选，外部进程)
  │   │   └── subprocess 调用
  │   └── pikepdf (Python 库)
  │       └── Pillow (图片处理)
  │
  ├── 并发控制
  │   ├── threading (标准库)
  │   └── threading.Semaphore
  │
  └── 文件处理
      ├── zipfile (标准库，批量打包)
      ├── io (标准库，内存缓冲)
      └── uuid (标准库，生成 ID)
```

---

## 9. 部署与运行

### 9.1 环境要求

- **Python**: 3.9+
- **操作系统**: Windows / macOS / Linux
- **可选**: Ghostscript（推荐，提升压缩效果）

### 9.2 快速启动

#### Windows

双击 [run.bat](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/run.bat)，或命令行：

```bat
python -m pip install flask pikepdf Pillow
python app.py
```

#### macOS / Linux

```bash
chmod +x start.sh
./start.sh
```

或手动：

```bash
pip3 install flask pikepdf Pillow
python3 app.py
```

### 9.3 服务访问

启动后自动打开浏览器，访问地址：

| 访问方式 | 地址 |
|----------|------|
| 本地访问 | `http://127.0.0.1:5050` |
| 局域网 | `http://<局域网IP>:5050` |

> 服务监听 `0.0.0.0:5050`，局域网内其他设备也可访问。

### 9.4 停止服务

按 `Ctrl+C` 停止 Flask 服务。

---

## 10. 构建打包

### 10.1 Windows 本地打包

**脚本**: [build_exe.bat](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/build_exe.bat)

**使用方法**: 双击运行，自动完成以下步骤：

1. 检测并打包 Ghostscript（如已安装）
2. 安装 Python 依赖（含 PyInstaller）
3. PyInstaller 打包（`--onedir` 模式）
4. 生成启动器 `启动.bat`

**输出位置**: `dist/PDF-Compress/`

**部署方式**: 将整个 `PDF-Compress` 文件夹复制到任意 Windows 电脑，双击 `启动.bat` 即可使用，无需安装 Python 或 Ghostscript。

### 10.2 PyInstaller 参数说明

```bash
pyinstaller --onedir --name "PDF-Compress" \
    --add-data "templates;templates" \    # 模板文件
    --add-data "static;static" \          # 静态资源
    --add-binary "gs_bundle\*;gs" \       # Ghostscript 二进制（可选）
    --collect-all pikepdf \               # 收集 pikepdf 全部资源
    --hidden-import pikepdf \             # 显式导入
    --hidden-import PIL._imaging \        # Pillow 底层模块
    --clean \
    app.py
```

### 10.3 CI 自动构建

**配置文件**: [.github/workflows/build-windows.yml](file:///Users/sailma/Documents/Claude/Product%20Design/PDF%20Compress/.github/workflows/build-windows.yml)

**触发条件**:
- push 到 `main` 分支
- 手动触发（`workflow_dispatch`）

**构建步骤**:
1. Checkout 代码
2. 设置 Python 3.11
3. 下载安装 Ghostscript 10.07.1
4. 安装 Python 依赖
5. PyInstaller 打包（内嵌 Ghostscript）
6. 生成启动器
7. 上传 artifact（保留 7 天）

**Artifact 名称**: `PDF-Compress-Windows`

---

## 附录

### A. 文件命名约定

| 模式 | 说明 |
|------|------|
| `{file_id}_in.pdf` | 上传的原始文件 |
| `{file_id}_out.pdf` | 压缩后的输出文件 |
| `compressed_batch_{batch_id}.zip` | 批量下载 ZIP |

### B. 线程安全说明

- `batch_state` 字典的所有读写操作均通过 `batch_lock` 保护
- `compress_semaphore` 控制并发压缩数量，避免系统过载
- 每个文件的压缩在独立线程中执行，异常不会影响其他文件

### C. 安全考虑

- 使用 `werkzeug.utils.secure_filename()` 处理文件名，防止路径遍历
- 文件大小限制：单文件隐含受 `MAX_CONTENT_LENGTH` (500MB) 限制
- 所有处理本地完成，数据不外传
- 前端使用 `escapeHtml()` 防止 XSS 注入

---

*文档版本: 1.0 | 最后更新: 2026-07-02*
