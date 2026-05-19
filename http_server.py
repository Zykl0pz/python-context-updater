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

# ─── Plantillas HTML ────────────────────────────────────────────────
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Servidor de archivos</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: system-ui, -apple-system, sans-serif; background: #f5f5f5; color: #333; }
        .header { background: #2c3e50; color: white; padding: 1rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }
        .header h1 { font-size: 1.2rem; }
        .breadcrumb { margin: 0.5rem 1rem; font-size: 0.9rem; }
        .breadcrumb a { color: #3498db; text-decoration: none; }
        .breadcrumb a:hover { text-decoration: underline; }
        .controls { padding: 0.5rem 1rem; display: flex; gap: 1rem; align-items: center; }
        .view-btn { background: #ecf0f1; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; }
        .view-btn.active { background: #3498db; color: white; }
        .grid-view { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 1rem; padding: 1rem; }
        .list-view { display: none; padding: 1rem; }
        .card { background: white; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); padding: 1rem; text-align: center; }
        .card img, .card .icon { width: 80px; height: 80px; object-fit: cover; display: block; margin: 0 auto 0.5rem; }
        .card .icon { font-size: 3rem; line-height: 80px; color: #7f8c8d; }
        .card .name { font-size: 0.85rem; word-break: break-word; margin-bottom: 0.5rem; }
        .download-btn { display: inline-block; background: #2ecc71; color: white; padding: 0.3rem 0.8rem; border-radius: 4px; text-decoration: none; font-size: 0.8rem; margin-top: 0.5rem; cursor: pointer; border: none; }
        .download-btn:hover { background: #27ae60; }
        table { width: 100%; border-collapse: collapse; background: white; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        th, td { padding: 0.6rem; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #ecf0f1; }
        .detail-icon { font-size: 1.5rem; margin-right: 0.5rem; vertical-align: middle; }
        .detail-img { width: 32px; height: 32px; object-fit: cover; vertical-align: middle; margin-right: 0.5rem; }
        @media (max-width: 600px) {
            .grid-view { grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); }
        }
        /* Modal de confirmación */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.5);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }
        .modal-overlay.active { display: flex; }
        .modal {
            background: white;
            padding: 2rem;
            border-radius: 8px;
            max-width: 400px;
            width: 90%;
            text-align: center;
            box-shadow: 0 10px 25px rgba(0,0,0,0.3);
        }
        .modal p { margin-bottom: 1.5rem; font-size: 1.1rem; }
        .modal-buttons { display: flex; gap: 1rem; justify-content: center; }
        .modal-buttons button {
            padding: 0.6rem 1.5rem;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 1rem;
        }
        .confirm-btn { background: #2ecc71; color: white; }
        .confirm-btn:hover { background: #27ae60; }
        .cancel-btn { background: #e74c3c; color: white; }
        .cancel-btn:hover { background: #c0392b; }
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
    <div id="list-view" class="list-view">
        <table>
            <thead>
                <tr><th>Nombre</th><th>Tamaño</th><th>Modificado</th><th>Descargar</th></tr>
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

    <script>
        const DATA = __DATA_PLACEHOLDER__;
        const CURRENT_PATH = __PATH_PLACEHOLDER__;

        // Referencias al modal
        const modal = document.getElementById('confirm-modal');
        const modalMessage = document.getElementById('modal-message');
        const confirmBtn = document.getElementById('modal-confirm');
        const cancelBtn = document.getElementById('modal-cancel');
        let pendingDownload = null; // { url, isDirectory, fileName }

        function render() {
            // Ruta actual (migas de pan)
            const breadcrumb = document.getElementById('path-display');
            const parts = CURRENT_PATH.split('/').filter(p => p);
            let html = '<a href="/">Inicio</a>';
            let accum = '';
            parts.forEach(part => {
                accum += '/' + part;
                html += ' / <a href="' + accum + '">' + decodeURIComponent(part) + '</a>';
            });
            breadcrumb.innerHTML = html || '/';

            // Vista de miniaturas
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
                let nameLink = item.type === 'directory'
                    ? '<a href="' + item.path + '/">' + item.name + '/</a>'
                    : '<span>' + item.name + '</span>';
                // Botón de descarga: archivos -> path directo; directorios -> path?download=zip
                let downloadBtn = '';
                if (item.type === 'file') {
                    downloadBtn = `<a class="download-btn" href="${item.path}" data-download="file" data-filename="${item.name}">⬇️ Descargar</a>`;
                } else {
                    downloadBtn = `<a class="download-btn" href="${item.path}?download=zip" data-download="directory" data-filename="${item.name}">⬇️ Descargar</a>`;
                }
                return `<div class="card">
                    ${iconHtml}
                    <div class="name">${nameLink}</div>
                    ${downloadBtn}
                </div>`;
            }).join('');

            // Vista de detalles
            const tbody = document.getElementById('list-tbody');
            tbody.innerHTML = DATA.map(item => {
                let iconCell = item.type === 'directory'
                    ? '<span class="detail-icon">📁</span>'
                    : (item.is_image ? '<img class="detail-img" src="' + item.path + '" alt="">' : '<span class="detail-icon">' + item.icon + '</span>');
                let nameCell = item.type === 'directory'
                    ? '<a href="' + item.path + '/">' + item.name + '/</a>'
                    : item.name;
                let sizeCell = item.type === 'directory' ? '-' : item.size_human;
                let downloadBtn = '';
                if (item.type === 'file') {
                    downloadBtn = `<a class="download-btn" href="${item.path}" data-download="file" data-filename="${item.name}">⬇️ Descargar</a>`;
                } else {
                    downloadBtn = `<a class="download-btn" href="${item.path}?download=zip" data-download="directory" data-filename="${item.name}">⬇️ Descargar</a>`;
                }
                return `<tr>
                    <td>${iconCell} ${nameCell}</td>
                    <td>${sizeCell}</td>
                    <td>${item.mtime}</td>
                    <td>${downloadBtn}</td>
                </tr>`;
            }).join('');
        }

        function switchView(view) {
            document.getElementById('grid-btn').classList.toggle('active', view === 'grid');
            document.getElementById('list-btn').classList.toggle('active', view === 'list');
            document.getElementById('grid-view').style.display = view === 'grid' ? 'grid' : 'none';
            document.getElementById('list-view').style.display = view === 'list' ? 'block' : 'none';
        }

        // Interceptar clics en botones de descarga (delegación de eventos)
        document.addEventListener('click', function(e) {
            const target = e.target.closest('.download-btn');
            if (!target) return;
            e.preventDefault();
            const downloadType = target.dataset.download;
            const fileName = target.dataset.filename;
            const url = target.getAttribute('href');
            // Mostrar modal
            let message = `¿Descargar "${fileName}"?`;
            if (downloadType === 'directory') {
                message += ' Se generará un archivo .zip con todo el contenido.';
            }
            modalMessage.textContent = message;
            pendingDownload = { url, downloadType, fileName };
            modal.classList.add('active');
        });

        // Eventos del modal
        confirmBtn.addEventListener('click', () => {
            if (!pendingDownload) return;
            const { url, downloadType, fileName } = pendingDownload;
            if (downloadType === 'file') {
                // Descarga directa usando un enlace temporal con download
                const a = document.createElement('a');
                a.href = url;
                a.download = fileName;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            } else {
                // Para directorios, navegar a la URL que generará el zip
                window.location.href = url;
            }
            closeModal();
        });

        cancelBtn.addEventListener('click', closeModal);
        // Cerrar modal al hacer clic fuera del contenido
        modal.addEventListener('click', function(e) {
            if (e.target === modal) closeModal();
        });

        function closeModal() {
            modal.classList.remove('active');
            pendingDownload = null;
        }

        // Inicializar
        render();
        switchView('grid'); // vista por defecto
    </script>
</body>
</html>"""

# ─── Utilidades ─────────────────────────────────────────────────────
def get_icon_for_file(name):
    """Devuelve un emoji representativo según la extensión del archivo."""
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
    """
    Devuelve la ruta absoluta real dentro de BASE_DIR.
    Lanza ValueError si intenta salir del directorio base.
    """
    parsed = urllib.parse.urlparse(requested_path)
    path = urllib.parse.unquote(parsed.path)
    full_path = (BASE_DIR / path.lstrip('/')).resolve()
    if BASE_DIR not in full_path.parents and full_path != BASE_DIR:
        raise ValueError("Acceso denegado")
    return full_path

def generate_directory_data(relative_path):
    """Genera lista de diccionarios con información de los elementos de un directorio."""
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
        item = {
            'name': name,
            'path': '/' + rel,  # ruta relativa desde la raíz del servidor
            'type': 'directory' if is_dir else 'file',
            'size': stat.st_size,
            'size_human': '-' if is_dir else human_readable_size(stat.st_size),
            'mtime': format_time(stat.st_mtime),
            'icon': get_icon_for_file(name),
            'is_image': not is_dir and is_image_file(name)
        }
        items.append(item)
    return items

def zip_directory(directory_path: Path):
    """
    Crea un archivo ZIP en memoria con el contenido del directorio.
    Retorna un objeto BytesIO con el zip.
    """
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
            # Analizar query string para detectar descarga de directorio
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            path_only = parsed.path

            # Si la ruta no termina en '/' y es un directorio, redirigir
            target = secure_path(path_only)
            if target.is_dir() and not path_only.endswith('/') and not query:
                self.send_response(301)
                self.send_header('Location', path_only + '/')
                self.end_headers()
                return

            # Descarga de directorio como ZIP
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
        """Genera y envía un archivo ZIP del directorio solicitado."""
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
        """Genera y envía la página HTML con la lista de archivos."""
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
        """Sirve un archivo con el tipo MIME adecuado."""
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