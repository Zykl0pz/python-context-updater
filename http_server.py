#!/usr/bin/env python3
"""
Servidor HTTP en puerto 8080 con interfaz personalizada.
Ejecutar desde la carpeta que se desea compartir:
    python3 servidor_ui.py
"""

import os
import sys
import io
import zipfile
import time
import urllib.parse
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# ─── Configuración ──────────────────────────────────────────────────
HOST = "0.0.0.0"
PORT = 8080
BASE_DIR = Path.cwd().resolve()  # Directorio raíz donde se ejecuta el script

# ─── Plantilla HTML con preview por botón y persistencia ───────────
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>Servidor de archivos</title>
    <style>
        :root {
            --color-bg: #f5f5f5;
            --color-text: #333;
            --color-primary: #2c3e50;
            --color-link: #3498db;
            --color-btn-active: #3498db;
            --color-download: #2ecc71;
            --color-download-hover: #27ae60;
            --color-preview: #3498db;
            --color-preview-hover: #2980b9;
            --shadow: 0 2px 5px rgba(0,0,0,0.1);
            --radius: 8px;
            --gap: clamp(0.5rem, 2vw, 1rem);
            --font-size-base: clamp(0.875rem, 2.5vw, 1rem);
            --font-size-small: clamp(0.75rem, 2vw, 0.85rem);
            --font-size-title: clamp(1rem, 3vw, 1.3rem);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: system-ui, -apple-system, sans-serif;
            background: var(--color-bg);
            color: var(--color-text);
            font-size: var(--font-size-base);
            line-height: 1.4;
            -webkit-text-size-adjust: 100%;
            padding-bottom: env(safe-area-inset-bottom);
        }

        .header {
            background: var(--color-primary);
            color: white;
            padding: var(--gap);
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 0.5rem;
        }
        .header h1 {
            font-size: var(--font-size-title);
            white-space: nowrap;
        }

        .breadcrumb {
            font-size: var(--font-size-small);
            opacity: 0.9;
            overflow-x: auto;
            white-space: nowrap;
            -webkit-overflow-scrolling: touch;
            padding: 0.25rem 0;
        }
        .breadcrumb a {
            color: white;
            text-decoration: underline;
        }
        .breadcrumb a:hover { opacity: 0.8; }

        .controls {
            padding: 0.75rem var(--gap);
            display: flex;
            flex-wrap: wrap;
            gap: var(--gap);
            align-items: center;
            background: white;
            border-bottom: 1px solid #ddd;
            position: sticky;
            top: 0;
            z-index: 10;
        }
        .view-btn {
            background: #ecf0f1;
            border: none;
            padding: 0.6rem 1.2rem;
            border-radius: var(--radius);
            cursor: pointer;
            font-size: var(--font-size-base);
            white-space: nowrap;
            flex: 1 1 auto;
            min-width: 100px;
            text-align: center;
            transition: background 0.2s, color 0.2s;
        }
        .view-btn.active {
            background: var(--color-btn-active);
            color: white;
        }

        .grid-view {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax( clamp(110px, 25vw, 200px), 1fr ));
            gap: var(--gap);
            padding: var(--gap);
        }
        .card {
            background: white;
            border-radius: var(--radius);
            box-shadow: var(--shadow);
            padding: var(--gap);
            text-align: center;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: space-between;
        }
        .card img, .card .icon {
            width: clamp(50px, 15vw, 80px);
            height: clamp(50px, 15vw, 80px);
            object-fit: cover;
            display: block;
            margin: 0 auto 0.5rem;
            flex-shrink: 0;
        }
        .card .icon {
            font-size: clamp(2rem, 10vw, 3rem);
            line-height: 1;
            color: #7f8c8d;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .card .name {
            font-size: var(--font-size-small);
            word-break: break-word;
            margin-bottom: 0.5rem;
            flex: 1;
        }
        .card-actions {
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
            justify-content: center;
            margin-top: 0.5rem;
        }
        .download-btn, .preview-btn {
            padding: 0.4em 0.8em;
            border-radius: var(--radius);
            text-decoration: none;
            font-size: var(--font-size-small);
            border: none;
            cursor: pointer;
            white-space: nowrap;
            display: inline-flex;
            align-items: center;
            gap: 0.2em;
        }
        .download-btn {
            background: var(--color-download);
            color: white;
        }
        .download-btn:hover { background: var(--color-download-hover); }
        .preview-btn {
            background: var(--color-preview);
            color: white;
        }
        .preview-btn:hover { background: var(--color-preview-hover); }

        .list-view {
            padding: var(--gap);
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }
        .list-view table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            box-shadow: var(--shadow);
            min-width: 550px;
        }
        th, td {
            padding: 0.6rem;
            text-align: left;
            border-bottom: 1px solid #ddd;
            font-size: var(--font-size-small);
        }
        th {
            background: #ecf0f1;
            white-space: nowrap;
            font-weight: 600;
        }
        .detail-icon {
            font-size: 1.5rem;
            vertical-align: middle;
            margin-right: 0.5rem;
        }
        .detail-img {
            width: 28px;
            height: 28px;
            object-fit: cover;
            vertical-align: middle;
            margin-right: 0.5rem;
            border-radius: 4px;
        }
        td:first-child {
            max-width: 200px;
            word-break: break-word;
        }

        /* Modales */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.5);
            z-index: 1000;
            justify-content: center;
            align-items: center;
            padding: 1rem;
        }
        .modal-overlay.active { display: flex; }
        .modal {
            background: white;
            padding: 2rem 1.5rem;
            border-radius: var(--radius);
            width: min(90vw, 400px);
            text-align: center;
            box-shadow: 0 10px 25px rgba(0,0,0,0.3);
        }
        .modal p {
            margin-bottom: 1.5rem;
            font-size: var(--font-size-base);
        }
        .modal-buttons {
            display: flex;
            gap: 1rem;
            justify-content: center;
            flex-wrap: wrap;
        }
        .modal-buttons button {
            padding: 0.7rem 1.5rem;
            border: none;
            border-radius: var(--radius);
            cursor: pointer;
            font-size: var(--font-size-base);
            flex: 1 1 auto;
            min-width: 100px;
        }
        .confirm-btn { background: var(--color-download); color: white; }
        .confirm-btn:hover { background: var(--color-download-hover); }
        .cancel-btn { background: #e74c3c; color: white; }
        .cancel-btn:hover { background: #c0392b; }

        /* Modal de preview (más ancho) */
        #preview-modal .modal {
            width: min(95vw, 900px);
            max-height: 90vh;
            padding: 1rem;
            overflow: auto;
            text-align: left;
        }
        #preview-modal .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }
        #preview-modal .close-preview {
            background: none;
            border: none;
            font-size: 1.5rem;
            cursor: pointer;
            color: #666;
        }
        #preview-content {
            max-height: 70vh;
            overflow: auto;
        }
        #preview-content img {
            max-width: 100%;
            height: auto;
            display: block;
            margin: 0 auto;
        }
        #preview-content pre {
            white-space: pre-wrap;
            word-wrap: break-word;
            background: #f0f0f0;
            padding: 1rem;
            border-radius: var(--radius);
            font-size: 0.85rem;
        }
        #preview-content audio, #preview-content video {
            width: 100%;
        }
        .preview-message {
            text-align: center;
            font-style: italic;
            color: #666;
        }

        @media (max-width: 480px) {
            .header {
                flex-direction: column;
                align-items: flex-start;
            }
            .controls {
                justify-content: center;
            }
            .grid-view {
                grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
            }
            .card .icon {
                font-size: 2.5rem;
            }
        }

        @media (min-width: 1024px) {
            .grid-view {
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            }
            .controls {
                padding-left: 2rem;
                padding-right: 2rem;
            }
            .list-view {
                padding-left: 2rem;
                padding-right: 2rem;
            }
            .breadcrumb {
                font-size: var(--font-size-base);
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>📁 Explorador de archivos</h1>
        <div id="path-display" class="breadcrumb"></div>
    </div>
    <div class="controls">
        <button id="grid-btn" class="view-btn active" onclick="switchView('grid')">🖼️ Miniaturas</button>
        <button id="list-btn" class="view-btn" onclick="switchView('list')">📋 Detalles</button>
    </div>
    <div id="grid-view" class="grid-view"></div>
    <div id="list-view" class="list-view" style="display:none">
        <table>
            <thead>
                <tr><th>Nombre</th><th>Tamaño</th><th>Modificado</th><th>Descargar</th><th>Vista previa</th></tr>
            </thead>
            <tbody id="list-tbody"></tbody>
        </table>
    </div>

    <!-- Modal de confirmación de descarga -->
    <div id="confirm-modal" class="modal-overlay">
        <div class="modal">
            <p id="modal-message">¿Descargar este elemento?</p>
            <div class="modal-buttons">
                <button id="modal-confirm" class="confirm-btn">Confirmar</button>
                <button id="modal-cancel" class="cancel-btn">Cancelar</button>
            </div>
        </div>
    </div>

    <!-- Modal de vista previa -->
    <div id="preview-modal" class="modal-overlay">
        <div class="modal">
            <div class="modal-header">
                <h3 id="preview-title">Vista previa</h3>
                <button class="close-preview" onclick="closePreview()">✖</button>
            </div>
            <div id="preview-content">
                <p class="preview-message">Cargando...</p>
            </div>
        </div>
    </div>

    <script>
        const DATA = __DATA_PLACEHOLDER__;
        const CURRENT_PATH = __PATH_PLACEHOLDER__;

        const modal = document.getElementById('confirm-modal');
        const modalMessage = document.getElementById('modal-message');
        const confirmBtn = document.getElementById('modal-confirm');
        const cancelBtn = document.getElementById('modal-cancel');
        const previewModal = document.getElementById('preview-modal');
        const previewContent = document.getElementById('preview-content');
        const previewTitle = document.getElementById('preview-title');
        let pendingDownload = null;

        // Persistencia de vista
        function getSavedViewMode() {
            return localStorage.getItem('viewMode') || 'grid';
        }
        function saveViewMode(mode) {
            localStorage.setItem('viewMode', mode);
        }

        function render() {
            const breadcrumb = document.getElementById('path-display');
            const parts = CURRENT_PATH.split('/').filter(p => p);
            let html = '<a href="/">Inicio</a>';
            let accum = '';
            parts.forEach(part => {
                accum += '/' + part;
                html += ' / <a href="' + accum + '">' + decodeURIComponent(part) + '</a>';
            });
            breadcrumb.innerHTML = html || '/';

            const grid = document.getElementById('grid-view');
            grid.innerHTML = DATA.map(item => {
                let iconHtml = '';
                if (item.type === 'directory') {
                    iconHtml = '<div class="icon">📁</div>';
                } else if (item.is_image) {
                    iconHtml = '<img src="' + item.path + '" alt="' + item.name + '" loading="lazy">';
                } else {
                    iconHtml = '<div class="icon">' + item.icon + '</div>';
                }

                let nameHtml;
                if (item.type === 'directory') {
                    nameHtml = '<a href="' + item.path + '/">' + item.name + '/</a>';
                } else {
                    nameHtml = '<span>' + item.name + '</span>';
                }

                let actionsHtml = '';
                if (item.type === 'file') {
                    actionsHtml = `<div class="card-actions">
                        <a class="download-btn" href="${item.path}" data-download="file" data-filename="${item.name}">⬇️ Descargar</a>
                        <button class="preview-btn" data-path="${item.path}" data-mime="${item.mime}" data-name="${item.name}">🔍 Vista previa</button>
                    </div>`;
                } else if (item.type === 'directory') {
                    actionsHtml = `<div class="card-actions">
                        <a class="download-btn" href="${item.path}?download=zip" data-download="directory" data-filename="${item.name}">⬇️ Descargar</a>
                    </div>`;
                }

                return `<div class="card">
                    ${iconHtml}
                    <div class="name">${nameHtml}</div>
                    ${actionsHtml}
                </div>`;
            }).join('');

            const tbody = document.getElementById('list-tbody');
            tbody.innerHTML = DATA.map(item => {
                let iconCell = item.type === 'directory'
                    ? '<span class="detail-icon">📁</span>'
                    : (item.is_image ? '<img class="detail-img" src="' + item.path + '" alt="">' : '<span class="detail-icon">' + item.icon + '</span>');
                let nameHtml;
                if (item.type === 'directory') {
                    nameHtml = '<a href="' + item.path + '/">' + item.name + '/</a>';
                } else {
                    nameHtml = '<span>' + item.name + '</span>';
                }
                let sizeCell = item.type === 'directory' ? '-' : item.size_human;
                let downloadCell = '';
                let previewCell = '';
                if (item.type === 'file') {
                    downloadCell = `<a class="download-btn" href="${item.path}" data-download="file" data-filename="${item.name}">⬇️ Descargar</a>`;
                    previewCell = `<button class="preview-btn" data-path="${item.path}" data-mime="${item.mime}" data-name="${item.name}">🔍 Vista previa</button>`;
                } else if (item.type === 'directory') {
                    downloadCell = `<a class="download-btn" href="${item.path}?download=zip" data-download="directory" data-filename="${item.name}">⬇️ Descargar</a>`;
                    previewCell = '-';
                }
                return `<tr>
                    <td>${iconCell} ${nameHtml}</td>
                    <td>${sizeCell}</td>
                    <td>${item.mtime}</td>
                    <td>${downloadCell}</td>
                    <td>${previewCell}</td>
                </tr>`;
            }).join('');
        }

        function switchView(view) {
            document.getElementById('grid-btn').classList.toggle('active', view === 'grid');
            document.getElementById('list-btn').classList.toggle('active', view === 'list');
            document.getElementById('grid-view').style.display = view === 'grid' ? 'grid' : 'none';
            document.getElementById('list-view').style.display = view === 'list' ? 'block' : 'none';
            saveViewMode(view);
        }

        // Preview con fetch, ahora usando rutas ya codificadas
        async function openPreview(filePath, mimeType, fileName) {
            previewTitle.textContent = fileName;
            previewContent.innerHTML = '<p class="preview-message">Cargando...</p>';
            previewModal.classList.add('active');

            try {
                const response = await fetch(filePath);
                if (!response.ok) throw new Error('Error al cargar');

                const mainType = mimeType.split('/')[0];
                const blob = await response.blob();
                const url = URL.createObjectURL(blob);

                if (mainType === 'image') {
                    previewContent.innerHTML = `<img src="${url}" alt="${fileName}">`;
                } else if (mainType === 'text' || mimeType === 'application/json' || mimeType === 'application/javascript' || mimeType === 'text/plain' || mimeType === 'application/xml') {
                    const text = await response.text();
                    previewContent.innerHTML = `<pre>${escapeHtml(text)}</pre>`;
                } else if (mainType === 'audio') {
                    previewContent.innerHTML = `<audio controls src="${url}"></audio>`;
                } else if (mainType === 'video') {
                    previewContent.innerHTML = `<video controls src="${url}"></video>`;
                } else if (mimeType === 'application/pdf') {
                    previewContent.innerHTML = `<iframe src="${url}" width="100%" height="500px" style="border:none;"></iframe>`;
                } else {
                    previewContent.innerHTML = `<p class="preview-message">Vista previa no disponible para este tipo de archivo.</p>
                    <p class="preview-message"><a href="${filePath}" download="${fileName}" class="download-btn">⬇️ Descargar</a></p>`;
                }
            } catch (err) {
                previewContent.innerHTML = `<p class="preview-message">No se pudo cargar la vista previa.</p>
                <p class="preview-message"><a href="${filePath}" download="${fileName}" class="download-btn">⬇️ Descargar</a></p>`;
            }
        }

        function closePreview() {
            previewModal.classList.remove('active');
            previewContent.innerHTML = '';
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Delegación de eventos: preview y descargas
        document.addEventListener('click', function(e) {
            // Preview por botón específico
            const previewBtn = e.target.closest('.preview-btn');
            if (previewBtn) {
                e.preventDefault();
                const path = previewBtn.dataset.path;
                const mime = previewBtn.dataset.mime;
                const name = previewBtn.dataset.name;
                openPreview(path, mime, name);
                return;
            }

            // Descargas con confirmación
            const downloadBtn = e.target.closest('.download-btn');
            if (downloadBtn) {
                e.preventDefault();
                const downloadType = downloadBtn.dataset.download;
                const fileName = downloadBtn.dataset.filename;
                const url = downloadBtn.getAttribute('href');
                let message = `¿Descargar "${fileName}"?`;
                if (downloadType === 'directory') {
                    message += ' Se generará un archivo .zip con todo el contenido.';
                }
                modalMessage.textContent = message;
                pendingDownload = { url, downloadType, fileName };
                modal.classList.add('active');
            }
        });

        // Modal de confirmación
        confirmBtn.addEventListener('click', () => {
            if (!pendingDownload) return;
            const { url, downloadType, fileName } = pendingDownload;
            if (downloadType === 'file') {
                const a = document.createElement('a');
                a.href = url;
                a.download = fileName;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            } else {
                window.location.href = url;
            }
            closeConfirmModal();
        });

        cancelBtn.addEventListener('click', closeConfirmModal);
        modal.addEventListener('click', function(e) {
            if (e.target === modal) closeConfirmModal();
        });

        function closeConfirmModal() {
            modal.classList.remove('active');
            pendingDownload = null;
        }

        // Cerrar preview con clic fuera
        previewModal.addEventListener('click', function(e) {
            if (e.target === previewModal) closePreview();
        });

        // Aplicar vista guardada y renderizar
        const savedView = getSavedViewMode();
        switchView(savedView);
        render();
    </script>
</body>
</html>"""

# ─── Utilidades ─────────────────────────────────────────────────────
def get_icon_for_file(name):
    ext = Path(name).suffix.lower()
    icons = {
        '.jpg': '🖼️', '.jpeg': '🖼️', '.png': '🖼️', '.gif': '🖼️', '.bmp': '🖼️', '.svg': '🖼️',
        '.mp4': '🎬', '.avi': '🎬', '.mkv': '🎬', '.mov': '🎬',
        '.mp3': '🎵', '.wav': '🎵', '.flac': '🎵', '.ogg': '🎵',
        '.pdf': '📕', '.doc': '📄', '.docx': '📄', '.xls': '📊', '.ppt': '📊',
        '.zip': '🗜️', '.rar': '🗜️', '.7z': '🗜️', '.tar': '🗜️', '.gz': '🗜️',
        '.py': '🐍', '.js': '📜', '.html': '🌐', '.css': '🎨', '.json': '📋',
        '.exe': '⚙️', '.dmg': '💿', '.iso': '💿',
    }
    return icons.get(ext, '📄')

def is_image_file(name):
    ext = Path(name).suffix.lower()
    return ext in {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp'}

def human_readable_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != 'B' else f"{size} B"
        size /= 1024
    return f"{size:.1f} TB"

def format_time(timestamp):
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(timestamp))

def secure_path(requested_path):
    parsed = urllib.parse.urlparse(requested_path)
    path = urllib.parse.unquote(parsed.path)
    full_path = (BASE_DIR / path.lstrip('/')).resolve()
    if BASE_DIR not in full_path.parents and full_path != BASE_DIR:
        raise ValueError("Acceso denegado")
    return full_path

def generate_directory_data(relative_path):
    abs_path = secure_path(relative_path)
    if not abs_path.is_dir():
        raise ValueError("No es un directorio")
    
    items = []
    try:
        entries = sorted(os.listdir(abs_path), key=lambda x: (not os.path.isdir(abs_path / x), x.lower()))
    except PermissionError:
        return items

    for name in entries:
        full = abs_path / name
        try:
            stat = full.stat()
        except OSError:
            continue
        is_dir = full.is_dir()
        rel = str(full.relative_to(BASE_DIR)).replace('\\', '/')
        # Codificar la ruta para URL (los espacios y caracteres especiales se convierten)
        rel_quoted = urllib.parse.quote(rel, safe='/')
        mime_type, _ = mimetypes.guess_type(str(full))
        if mime_type is None:
            mime_type = 'application/octet-stream'
        item = {
            'name': name,
            'path': '/' + rel_quoted,   # ruta lista para usar en URLs
            'type': 'directory' if is_dir else 'file',
            'size': stat.st_size,
            'size_human': '-' if is_dir else human_readable_size(stat.st_size),
            'mtime': format_time(stat.st_mtime),
            'icon': get_icon_for_file(name),
            'is_image': not is_dir and is_image_file(name),
            'mime': mime_type
        }
        items.append(item)
    return items

def zip_directory(directory_path: Path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                full_path = Path(root) / file
                arcname = full_path.relative_to(directory_path)
                zf.write(full_path, arcname)
    buffer.seek(0)
    return buffer

# ─── Manejador HTTP ─────────────────────────────────────────────────
class CustomHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            path_only = parsed.path

            target = secure_path(path_only)
            if target.is_dir() and not path_only.endswith('/') and not query:
                self.send_response(301)
                self.send_header('Location', path_only + '/')
                self.end_headers()
                return

            if target.is_dir() and 'download' in query and query['download'][0] == 'zip':
                self.serve_directory_zip(target)
                return

            if target.is_dir():
                self.serve_directory_listing(path_only)
            elif target.is_file():
                self.serve_file(target)
            else:
                self.send_error(404, "No encontrado")
        except ValueError:
            self.send_error(403, "Prohibido")
        except Exception as e:
            self.send_error(500, str(e))

    def serve_directory_zip(self, dir_path: Path):
        try:
            zip_buffer = zip_directory(dir_path)
            zip_name = dir_path.name + '.zip'
            self.send_response(200)
            self.send_header('Content-Type', 'application/zip')
            self.send_header('Content-Disposition', f'attachment; filename="{zip_name}"')
            self.send_header('Content-Length', str(len(zip_buffer.getvalue())))
            self.end_headers()
            self.wfile.write(zip_buffer.read())
        except Exception as e:
            self.send_error(500, f"Error al crear ZIP: {e}")

    def serve_directory_listing(self, requested_path):
        display_path = requested_path if requested_path.endswith('/') else requested_path + '/'
        try:
            items = generate_directory_data(display_path)
        except Exception:
            self.send_error(500, "Error al leer directorio")
            return

        import json
        data_json = json.dumps(items)
        current_rel = urllib.parse.unquote(urllib.parse.urlparse(requested_path).path)
        if not current_rel.endswith('/'):
            current_rel += '/'
        current_rel = current_rel.rstrip('/')

        html = HTML_TEMPLATE.replace('__DATA_PLACEHOLDER__', data_json)
        html = html.replace('__PATH_PLACEHOLDER__', json.dumps(current_rel))

        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def serve_file(self, file_path):
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type is None:
            mime_type = 'application/octet-stream'

        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', mime_type)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except OSError:
            self.send_error(404, "Archivo no encontrado")

    def log_message(self, format, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {args[0]}\n")

# ─── Punto de entrada ───────────────────────────────────────────────
def main():
    server = HTTPServer((HOST, PORT), CustomHandler)
    print(f"🚀 Servidor iniciado en http://{HOST}:{PORT}")
    print(f"📂 Sirviendo el directorio: {BASE_DIR}")
    print("Presiona Ctrl+C para detener.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Servidor detenido.")
        server.server_close()

if __name__ == '__main__':
    main()