"""
PDF 压缩服务 - 本地部署版 v2.0
基于 Flask + pikepdf，支持多文件批量压缩、实时进度、并发控制
"""

import os
import io
import sys
import uuid
import time
import socket
import shutil
import subprocess
import threading
import webbrowser
import zipfile
from pathlib import Path

from flask import Flask, request, jsonify, send_file, render_template
from werkzeug.utils import secure_filename

# ─── 路径处理（兼容 PyInstaller 打包）────────────────────────────
if getattr(sys, 'frozen', False):
    # PyInstaller 打包后：资源在 _MEIPASS，可写数据在 exe 同级目录
    BUNDLE_DIR = sys._MEIPASS
    DATA_DIR = os.path.dirname(sys.executable)
else:
    # 源码运行
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = BUNDLE_DIR

app = Flask(
    __name__,
    template_folder=os.path.join(BUNDLE_DIR, 'templates'),
    static_folder=os.path.join(BUNDLE_DIR, 'static'),
)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB 总上传限制
app.config['UPLOAD_FOLDER'] = os.path.join(DATA_DIR, 'uploads')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ─── 并发控制 ─────────────────────────────────────────────────────
MAX_CONCURRENT = 2
compress_semaphore = threading.Semaphore(MAX_CONCURRENT)

# ─── 批次状态存储 ─────────────────────────────────────────────────
batch_state = {}  # batch_id → {files, total, completed, all_done, level, created_at}
batch_lock = threading.Lock()


# ─── 定时清理 ─────────────────────────────────────────────────────
def cleanup_old_files():
    """清理超过 30 分钟的临时文件和批次状态"""
    now = time.time()
    for f in Path(app.config['UPLOAD_FOLDER']).glob('*'):
        if now - f.stat().st_mtime > 1800:
            try:
                f.unlink()
            except OSError:
                pass

    with batch_lock:
        expired = [
            bid for bid, b in batch_state.items()
            if now - b.get('created_at', 0) > 1800
        ]
        for bid in expired:
            del batch_state[bid]


# ─── Ghostscript 检测 ──────────────────────────────────────────────
_GS_EXECUTABLE = None
_GS_CHECKED = False

def _detect_ghostscript():
    """检测系统中可用的 Ghostscript 可执行文件（含 PyInstaller 内嵌）"""
    global _GS_EXECUTABLE, _GS_CHECKED
    if _GS_CHECKED:
        return _GS_EXECUTABLE is not None
    _GS_CHECKED = True

    # 1. PyInstaller 打包时内嵌的 Ghostscript
    if getattr(sys, 'frozen', False):
        for exe_name in ['gswin64c.exe', 'gswin32c.exe', 'gs']:
            bundled = os.path.join(sys._MEIPASS, 'gs', exe_name)
            if os.path.isfile(bundled):
                _GS_EXECUTABLE = bundled
                return True

    # 2. 系统 PATH 中的 Ghostscript
    for candidate in ['gs', 'gswin64c', 'gswin32c']:
        if shutil.which(candidate):
            _GS_EXECUTABLE = candidate
            return True

    # 3. Windows 常见安装位置
    if sys.platform == 'win32':
        for base in [os.environ.get('ProgramFiles', 'C:\\Program Files'),
                       os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)')]:
            for ver in ['10.07.1', '10.07.0', '10.06.0', '10.05.0']:
                for exe in ['gswin64c.exe', 'gswin32c.exe']:
                    p = os.path.join(base, 'gs', 'gs' + ver.replace('.', ''), 'bin', exe)
                    if os.path.isfile(p):
                        _GS_EXECUTABLE = p
                        return True

    return False

def has_ghostscript():
    """返回 Ghostscript 是否可用（自动缓存结果）"""
    return _detect_ghostscript()


def compress_with_ghostscript(input_path: str, output_path: str, level: str = 'standard') -> dict:
    """
    使用 Ghostscript 压缩 PDF（工业标准，效果远超 pikepdf）

    Ghostscript 会重新渲染整个 PDF，真正降采样图片、子集化字体、
    优化色彩空间，是所有 PDF 压缩工具的底层引擎。
    """
    # 映射到 Ghostscript PDFSETTINGS
    # /printer=300dpi（高清） /ebook=150dpi（文字清晰+压缩好） /screen=72dpi（文字模糊，不用）
    gs_presets = {
        'standard': '/printer',   # 300 dpi，近乎无损
        'extreme':  '/ebook',     # 150 dpi，文字清晰 + 图片压缩 + 字体子集化
    }
    preset = gs_presets.get(level, '/ebook')

    cmd = [
        _GS_EXECUTABLE,
        '-sDEVICE=pdfwrite',
        '-dCompatibilityLevel=1.5',
        '-dPDFSETTINGS={}'.format(preset),
        '-dNOPAUSE',
        '-dQUIET',
        '-dBATCH',
        '-dEmbedAllFonts=false',       # 不嵌入原文件未嵌入的字体（防膨胀）
        '-dCompressFonts=true',
        '-dSubsetFonts=true',
        '-dOptimize=true',
        '-dDetectDuplicateImages=true',
        '-dPreserveHalftoneInfo=false',
        '-sOutputFile={}'.format(output_path),
        input_path,
    ]

    try:
        # 设置 5 分钟超时，大文件可能需要较长时间
        subprocess.run(cmd, check=True, timeout=300,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise RuntimeError('文件过大，压缩超时（>5分钟），请尝试轻量压缩')
    except subprocess.CalledProcessError as e:
        raise RuntimeError('Ghostscript 压缩失败，PDF 可能已损坏')
    except FileNotFoundError:
        raise RuntimeError('未找到 Ghostscript，请安装后重试')

    original_size = os.path.getsize(input_path)
    compressed_size = os.path.getsize(output_path)
    ratio = round((1 - compressed_size / original_size) * 100, 1) if original_size > 0 else 0

    return {
        'original_size': original_size,
        'compressed_size': compressed_size,
        'ratio': ratio,
        'engine': 'ghostscript',
    }


# ─── 压缩核心逻辑（智能引擎调度）─────────────────────────────────
def compress_pdf(input_path: str, output_path: str, level: str = 'standard') -> dict:
    """
    智能压缩：自动选择最优引擎

    策略：
    1. standard/extreme + Ghostscript → 先试 GS
    2. GS 结果若 ≥ 原始大小 → 回退 pikepdf（防字体嵌入膨胀）
    3. light → 仅 pikepdf（轻量优化不改内容）
    """
    import pikepdf

    original_size = os.path.getsize(input_path)

    # ── Ghostscript 尝试（standard/extreme） ──────────────────────
    if level in ('standard', 'extreme') and has_ghostscript():
        try:
            gs_result = compress_with_ghostscript(input_path, output_path, level)
            # 如果 GS 没有变小（甚至变大），自动回退到 pikepdf
            if gs_result['compressed_size'] < original_size:
                return gs_result
            # GS 回退：重新用 pikepdf 压缩
        except Exception:
            pass  # GS 失败也回退

    # ── pikepdf 压缩 ──────────────────────────────────────────────
    result = _compress_pdf_pikepdf(input_path, output_path, level)
    return result


def _compress_pdf_pikepdf(input_path: str, output_path: str, level: str = 'standard') -> dict:
    """使用 pikepdf + Pillow 压缩 PDF（回退引擎）"""
    import pikepdf

    original_size = os.path.getsize(input_path)
    pdf = pikepdf.Pdf.open(input_path)

    configs = {
        'light': {
            'max_dim': None, 'jpeg_quality': None,
            'convert_to_jpeg': False, 'strip_metadata': True,
            'remove_unreferenced': True, 'recompress_flate': False,
        },
        'standard': {
            'max_dim': 2000, 'jpeg_quality': 85,
            'convert_to_jpeg': True, 'strip_metadata': True,
            'remove_unreferenced': True, 'recompress_flate': True,
        },
        'extreme': {
            'max_dim': 1200, 'jpeg_quality': 55,
            'convert_to_jpeg': True, 'strip_metadata': True,
            'remove_unreferenced': True, 'recompress_flate': True,
        },
    }
    cfg = configs.get(level, configs['standard'])

    if cfg['convert_to_jpeg'] or cfg['max_dim']:
        try:
            from PIL import Image as PILImage
            for page in pdf.pages:
                _process_page_images(page, PILImage, io, cfg)
        except ImportError:
            pass

    if cfg['strip_metadata']:
        try:
            with pdf.open_metadata() as meta:
                for key in list(meta.keys()):
                    try:
                        del meta[key]
                    except Exception:
                        pass
        except Exception:
            pass

    if cfg['remove_unreferenced']:
        pdf.remove_unreferenced_resources()

    pdf.save(
        output_path,
        linearize=True,
        compress_streams=True,
        object_stream_mode=pikepdf.ObjectStreamMode.generate,
        recompress_flate=cfg['recompress_flate'],
        stream_decode_level=pikepdf.StreamDecodeLevel.specialized,
    )

    compressed_size = os.path.getsize(output_path)
    ratio = round((1 - compressed_size / original_size) * 100, 1) if original_size > 0 else 0

    return {
        'original_size': original_size,
        'compressed_size': compressed_size,
        'ratio': ratio,
        'engine': 'pikepdf',
    }


def _process_page_images(page, PILImage, io_module, cfg):
    """
    处理页面中的所有图片 —— 这是压缩的核心

    三步曲：
    1. 降采样：把过大像素的图片等比缩小（最长边限制）
    2. 格式转换：RGBA/CMYK/P → RGB → JPEG（大幅减小体积）
    3. 重新编码：用指定质量写入 JPEG，替换原始图片流

    兼容 FlateDecode+Prediction（常见于 ERP/报表系统生成的 PDF），
    通过 pikepdf.PdfImage 包装来解码。
    """
    import pikepdf

    max_dim = cfg.get('max_dim')
    jpeg_quality = cfg.get('jpeg_quality', 70)

    for name, image in list(page.images.items()):
        try:
            # FlateDecode+Prediction 等格式需要通过 PdfImage 解码
            pdf_img = pikepdf.PdfImage(image)
            pil_image = pdf_img.as_pil_image()
            w, h = pil_image.size
            original_bytes = len(image.read_raw_bytes())

            # 1. 降采样（只对超过限制的图片操作）
            if max_dim and max(w, h) > max_dim:
                ratio = max_dim / max(w, h)
                if ratio < 0.95:
                    new_size = (int(w * ratio), int(h * ratio))
                    pil_image = pil_image.resize(new_size, PILImage.LANCZOS)

            # 2. 色彩空间 → RGB（JPEG 不支持透明/CMYK）
            if pil_image.mode == 'RGBA':
                bg = PILImage.new('RGB', pil_image.size, (255, 255, 255))
                bg.paste(pil_image, mask=pil_image.split()[3])
                pil_image = bg
            elif pil_image.mode in ('CMYK', 'P', 'PA', 'LA'):
                pil_image = pil_image.convert('RGB')
            elif pil_image.mode not in ('RGB', 'L'):
                pil_image = pil_image.convert('RGB')

            # 3. JPEG 编码
            out = io_module.BytesIO()
            pil_image.save(out, format='JPEG', quality=jpeg_quality, optimize=True)
            out.seek(0)
            jpeg_bytes = out.read()

            # 4. 如果 JPEG 比原图还大，保留原图不替换
            if len(jpeg_bytes) >= original_bytes:
                continue

            # 5. 替换 PDF 图片流
            new_stream = pikepdf.Stream(pdf=page.obj, data=jpeg_bytes)
            new_stream.Subtype = pikepdf.Name('/Image')
            new_stream.Width = pil_image.width
            new_stream.Height = pil_image.height
            new_stream.BitsPerComponent = 8
            new_stream.Filter = pikepdf.Name('/DCTDecode')
            new_stream.ColorSpace = (
                pikepdf.Name('/DeviceGray') if pil_image.mode == 'L'
                else pikepdf.Name('/DeviceRGB')
            )
            page.images[name] = new_stream

        except Exception:
            continue


# ─── 批次处理（后台线程）─────────────────────────────────────────
def process_batch(batch_id: str):
    """后台线程：并发处理批次中的所有文件，Semaphore 限制并发数"""
    try:
        with batch_lock:
            batch = batch_state.get(batch_id)
            if not batch:
                return
            files = list(batch['files'])  # 复制引用，安全遍历

        def process_one(f: dict):
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{f['id']}_in.pdf")
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{f['id']}_out.pdf")

            with compress_semaphore:
                # 拿到并发槽位后才标记为「压缩中」
                with batch_lock:
                    f['status'] = 'compressing'

                try:
                    result = compress_pdf(input_path, output_path, batch['level'])
                    with batch_lock:
                        f['status'] = 'done'
                        f['original_size'] = result['original_size']
                        f['compressed_size'] = result['compressed_size']
                        f['ratio'] = result['ratio']
                        f['engine'] = result.get('engine', 'pikepdf')
                        batch['completed'] += 1
                except Exception as e:
                    with batch_lock:
                        f['status'] = 'error'
                        f['error'] = str(e)
                        batch['completed'] += 1

        # 为每个文件启动独立线程，Semaphore 自动排队
        threads = []
        for f in files:
            t = threading.Thread(target=process_one, args=(f,), daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

    finally:
        with batch_lock:
            if batch_id in batch_state:
                batch_state[batch_id]['all_done'] = True


# ─── 路由 ───────────────────────────────────────────────────────
@app.route('/')
def index():
    """首页"""
    cleanup_old_files()
    return render_template('index.html', has_ghostscript=has_ghostscript())


@app.route('/upload', methods=['POST'])
def upload():
    """上传多文件并开始批量压缩"""
    cleanup_old_files()

    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'success': False, 'error': '未找到上传文件'}), 400

    level = request.form.get('level', 'standard')
    if level not in ('light', 'standard', 'extreme'):
        level = 'standard'

    batch_id = uuid.uuid4().hex[:12]
    file_infos = []

    for file in files:
        if file.filename == '':
            continue
        if not file.filename.lower().endswith('.pdf'):
            continue

        file_id = uuid.uuid4().hex[:12]
        safe_name = secure_filename(file.filename) or 'document.pdf'
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{file_id}_in.pdf')

        try:
            file.save(input_path)
            file_infos.append({
                'id': file_id,
                'name': safe_name,
                'status': 'queued',
                'original_size': None,
                'compressed_size': None,
                'ratio': None,
                'error': None,
            })
        except Exception as e:
            return jsonify({'success': False, 'error': f'保存文件失败: {str(e)}'}), 500

    if not file_infos:
        return jsonify({'success': False, 'error': '没有有效的 PDF 文件'}), 400

    # 注册批次
    with batch_lock:
        batch_state[batch_id] = {
            'files': file_infos,
            'level': level,
            'total': len(file_infos),
            'completed': 0,
            'all_done': False,
            'created_at': time.time(),
        }

    # 启动后台处理
    threading.Thread(target=process_batch, args=(batch_id,), daemon=True).start()

    return jsonify({
        'success': True,
        'batch_id': batch_id,
        'total': len(file_infos),
        'files': [{'id': f['id'], 'name': f['name']} for f in file_infos],
    })


@app.route('/status/<batch_id>')
def status(batch_id):
    """查询批次处理进度"""
    with batch_lock:
        batch = batch_state.get(batch_id)
        if not batch:
            return jsonify({'error': '批次不存在或已过期'}), 404

        return jsonify({
            'batch_id': batch_id,
            'total': batch['total'],
            'completed': batch['completed'],
            'all_done': batch['all_done'],
            'level': batch['level'],
            'files': [
                {
                    'id': f['id'],
                    'name': f['name'],
                    'status': f['status'],
                    'original_size': f.get('original_size'),
                    'compressed_size': f.get('compressed_size'),
                    'ratio': f.get('ratio'),
                    'error': f.get('error'),
                    'engine': f.get('engine', 'pikepdf'),
                }
                for f in batch['files']
            ],
        })


@app.route('/download/<file_id>')
def download(file_id):
    """下载单个压缩后的 PDF"""
    safe_id = secure_filename(file_id)
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{safe_id}_out.pdf')

    if not os.path.exists(output_path):
        return jsonify({'success': False, 'error': '文件已过期，请重新上传'}), 404

    return send_file(
        output_path,
        as_attachment=True,
        download_name=f'compressed_{safe_id}.pdf',
        mimetype='application/pdf',
    )


@app.route('/download-all/<batch_id>')
def download_all(batch_id):
    """打包下载批次中所有已完成的压缩文件"""
    with batch_lock:
        batch = batch_state.get(batch_id)

    if not batch:
        return jsonify({'error': '批次不存在或已过期'}), 404

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in batch['files']:
            if f['status'] == 'done':
                output_path = os.path.join(
                    app.config['UPLOAD_FOLDER'], f"{f['id']}_out.pdf"
                )
                if os.path.exists(output_path):
                    zip_name = f['name'].replace('.pdf', '_compressed.pdf')
                    zf.write(output_path, zip_name)

    buf.seek(0)

    if buf.getbuffer().nbytes == 0:
        return jsonify({'error': '没有可下载的文件'}), 404

    return send_file(
        buf,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'compressed_batch_{batch_id}.zip',
    )


# ─── 启动 ───────────────────────────────────────────────────────
if __name__ == '__main__':
    HOST = '0.0.0.0'
    PORT = 5050

    print('=' * 56)
    print('  📄 PDF 压缩服务 v2.0')
    print('  支持多文件批量压缩 | 并发上限: {} 个'.format(MAX_CONCURRENT))
    print('  本地访问: http://127.0.0.1:{}'.format(PORT))

    # 获取局域网 IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(('10.255.255.255', 1))
        lan_ip = s.getsockname()[0]
        s.close()
        if lan_ip and not lan_ip.startswith('127.'):
            print('  局域网访问: http://{}:{}'.format(lan_ip, PORT))
    except Exception:
        pass

    print('  按 Ctrl+C 停止服务')
    print('=' * 56)

    # 自动打开浏览器
    webbrowser.open('http://127.0.0.1:{}'.format(PORT))

    app.run(host=HOST, port=PORT, debug=False)
