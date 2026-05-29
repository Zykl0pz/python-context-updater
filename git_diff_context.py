#!/usr/bin/env python3
"""
Generador universal de diferencias Git (todas las mejoras integradas)
Interactivo, con perfil, filtros, diff unificado, HTML, parches, watch, etc.
"""

import os
import sys
import subprocess
import json
import xml.etree.ElementTree as ET
import platform
import getpass
import argparse
import fnmatch
import hashlib
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple, Any

# ─── Dependencias opcionales ───────────────────────────────────────────────
try:
    from charset_normalizer import from_bytes
    HAS_CHARSET = True
except ImportError:
    HAS_CHARSET = False

try:
    import pathspec
    HAS_PATHSPEC = True
except ImportError:
    HAS_PATHSPEC = False

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

try:
    import pygments
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.formatters import HtmlFormatter
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False

try:
    import pyperclip
    HAS_CLIPBOARD = True
except ImportError:
    HAS_CLIPBOARD = False

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False

# ─── Colores ANSI ──────────────────────────────────────────────────────────
class Colors:
    HEADER = '\033[95m'; BLUE = '\033[94m'; CYAN = '\033[96m'
    GREEN = '\033[92m'; WARNING = '\033[93m'; FAIL = '\033[91m'
    ENDC = '\033[0m'; BOLD = '\033[1m'; UNDERLINE = '\033[4m'

def colored(text: str, color: str) -> str:
    return f"{color}{text}{Colors.ENDC}" if sys.stdout.isatty() else text

# ─── Utilidades generales ──────────────────────────────────────────────────
def format_size(size_bytes: int) -> str:
    for unit in ['B','KB','MB','GB','TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}PB"

def detect_encoding(filepath: Path) -> str:
    if HAS_CHARSET:
        try:
            with open(filepath, 'rb') as f:
                raw = f.read(8192)
            result = from_bytes(raw)
            if result.best():
                return result.best().encoding
        except:
            pass
    for enc in ['utf-8', 'latin-1', 'cp1252']:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                f.read(1024)
            return enc
        except:
            continue
    return 'utf-8'

def is_binary(filepath: Path) -> bool:
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(8192)
            return b'\0' in chunk
    except:
        return True

def get_language(ext: str, filename: str = '') -> str:
    lang_map = {
        '.py':'Python','.js':'JavaScript','.ts':'TypeScript','.java':'Java',
        '.c':'C','.cpp':'C++','.go':'Go','.rs':'Rust','.md':'Markdown',
        '.json':'JSON','.xml':'XML','.yaml':'YAML','.yml':'YAML','.sh':'Bash',
        '.bat':'Batch','.ps1':'PowerShell','.rb':'Ruby','.php':'PHP','.html':'HTML',
        '.css':'CSS','.sql':'SQL','.txt':'Text'
    }
    if ext in lang_map:
        return lang_map[ext]
    if filename in {'.env', '.env.example', '.env.local'}:
        return 'ENV'
    return 'Texto'

def get_git_repo_root() -> Path:
    try:
        root = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip()
        return Path(root)
    except:
        return Path.cwd()

def get_current_branch() -> str:
    try:
        return subprocess.check_output(['git', 'branch', '--show-current'], text=True).strip()
    except:
        return 'detached'

def get_last_commit() -> Dict[str, str]:
    try:
        output = subprocess.check_output(['git', 'log', '-1', '--format=%H%n%s%n%an%n%ae%n%ad'], text=True).strip().splitlines()
        return {'hash': output[0], 'subject': output[1], 'author': output[2], 'email': output[3], 'date': output[4]}
    except:
        return {}

# ─── Filtros de .contextignore ────────────────────────────────────────────
def load_contextignore(start_path: Path = None) -> List[str]:
    if start_path is None:
        start_path = Path.cwd()
    ignore_file = start_path / '.contextignore'
    if not ignore_file.exists():
        default_dirs = ['__pycache__/', 'node_modules/', 'dist/', 'build/', '.git/', '.idea/']
        with open(ignore_file, 'w') as f:
            f.write('\n'.join(default_dirs) + '\n')
        return default_dirs
    with open(ignore_file, 'r') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]

def should_ignore(rel_path: str, patterns: List[str]) -> bool:
    path = rel_path.replace(os.sep, '/')
    for pat in patterns:
        if pat.endswith('/'):
            if path == pat.rstrip('/') or path.startswith(pat):
                return True
        else:
            if fnmatch.fnmatch(path, pat):
                return True
    return False

# ─── Obtención de cambios (con soporte para dos referencias) ──────────────
def get_all_changes(ref_a: str = 'HEAD', ref_b: str = None, subdir: str = '.') -> List[Dict]:
    """
    Obtiene cambios entre ref_a y ref_b.
    Si ref_b es None, compara working directory con ref_a.
    Retorna lista con path, status (M, A, D, U, R, C).
    """
    if ref_b is None:
        # Comparar working directory vs ref_a (status porcelana)
        try:
            output = subprocess.check_output(['git', 'status', '--porcelain', '--', subdir], text=True, stderr=subprocess.DEVNULL)
        except:
            return []
    else:
        # Comparar dos commits
        try:
            output = subprocess.check_output(['git', 'diff', '--name-status', f'{ref_a}..{ref_b}', '--', subdir], text=True, stderr=subprocess.DEVNULL)
            # Convertir a formato similar: 'M\tpath'
            changes = []
            for line in output.strip().splitlines():
                if not line:
                    continue
                parts = line.split(maxsplit=1)
                if len(parts) != 2:
                    continue
                status, path = parts[0], parts[1]
                # M, A, D, R, etc.
                changes.append({'path': path, 'status': status[0]})
            return changes
        except:
            return []
    # Parsear git status --porcelain
    changes = []
    for line in output.strip().splitlines():
        if not line:
            continue
        status_code = line[:2]
        rest = line[3:].strip()
        x, y = status_code[0], status_code[1]
        if y == 'M' or x == 'M':
            final_status = 'M'
        elif y == 'D' or x == 'D':
            final_status = 'D'
        elif y == 'A' or x == 'A':
            final_status = 'A'
        elif y == 'R' or x == 'R':
            final_status = 'R'
            # Formato: "R  old -> new"
            if ' -> ' in rest:
                new_path = rest.split(' -> ')[1]
                changes.append({'path': new_path, 'status': final_status, 'old_path': rest.split(' -> ')[0]})
                continue
        elif y == '?' and x == '?':
            final_status = 'U'
        else:
            continue
        changes.append({'path': rest, 'status': final_status})
    return changes

def get_original_content(ref: str, filepath: str) -> Optional[str]:
    try:
        return subprocess.check_output(['git', 'show', f'{ref}:{filepath}'], text=True, stderr=subprocess.DEVNULL)
    except:
        return None

def get_current_content(filepath: Path) -> Optional[str]:
    if not filepath.exists():
        return None
    if is_binary(filepath):
        return None
    encoding = detect_encoding(filepath)
    try:
        with open(filepath, 'r', encoding=encoding, errors='replace') as f:
            return f.read()
    except:
        return None

def get_unified_diff(ref_a: str, ref_b: str = None, filepath: str = None, context_lines: int = 3) -> str:
    """Obtiene diff unificado de un archivo entre ref_a y ref_b (o WD si ref_b None)."""
    if ref_b is None:
        cmd = ['git', 'diff', f'-U{context_lines}', ref_a, '--', filepath]
    else:
        cmd = ['git', 'diff', f'-U{context_lines}', f'{ref_a}..{ref_b}', '--', filepath]
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
    except:
        return "[No se pudo generar diff]"

# ─── Clase para cache de contenidos originales ────────────────────────────
class ContentCache:
    def __init__(self):
        self._cache = {}
    def get_original(self, ref: str, path: str) -> Optional[str]:
        key = f"{ref}:{path}"
        if key not in self._cache:
            self._cache[key] = get_original_content(ref, path)
        return self._cache[key]
    def clear(self):
        self._cache.clear()

# ─── Menú interactivo y perfil ────────────────────────────────────────────
def load_profile(profile_path: Path) -> Optional[Dict]:
    if profile_path.exists():
        try:
            with open(profile_path, 'r') as f:
                return json.load(f)
        except:
            pass
    return None

def save_profile(profile_path: Path, profile: Dict):
    try:
        with open(profile_path, 'w') as f:
            json.dump(profile, f, indent=2)
        print(colored(f"Perfil guardado en {profile_path}", Colors.GREEN))
    except Exception as e:
        print(colored(f"No se pudo guardar perfil: {e}", Colors.WARNING))

def interactive_menu(profile: Optional[Dict] = None) -> Dict:
    """Devuelve configuración: ref_a, ref_b, subdir, status_filters, ext_filters, diff_style, output_format, compact, line_numbers, etc."""
    print(colored("\n=== CONFIGURACIÓN DEL INFORME ===", Colors.BOLD))
    # 1. Comparar entre commits o con working directory
    if profile and 'ref_a' in profile:
        ref_a = profile['ref_a']
        ref_b = profile.get('ref_b')
        print(colored(f"Referencias cargadas: {ref_a} -> {ref_b if ref_b else 'Working Directory'}", Colors.GREEN))
    else:
        ref_a = input(colored("Referencia base (commit, tag, rama) [HEAD]: ", Colors.CYAN)).strip() or 'HEAD'
        ref_b = input(colored("Referencia destino (vacío para Working Directory): ", Colors.CYAN)).strip() or None
    # 2. Subdirectorio
    subdir = input(colored("Subdirectorio a analizar (vacío para raíz): ", Colors.CYAN)).strip() or '.'
    # 3. Filtros por estado
    print(colored("\nFiltrar por tipo de cambio (múltiples, ej. M,A,U):", Colors.HEADER))
    print("Opciones: M=Modificado, A=Agregado(staged), D=Eliminado, U=Untracked, R=Renombrado, C=Copiado, all=todos")
    status_choice = input(colored("Selecciona: [all]: ", Colors.CYAN)).strip().lower() or 'all'
    if status_choice == 'all':
        status_filters = ['M','A','D','U','R','C']
    else:
        status_filters = [s.upper() for s in status_choice.split(',') if s.upper() in 'MADURC']
    # 4. Filtros por extensión/patrón
    inc_ext = input(colored("Extensiones a incluir (ej. .py,.md) o vacío para todos: ", Colors.CYAN)).strip()
    inc_ext_list = [e.strip().lower() for e in inc_ext.split(',')] if inc_ext else []
    exc_pattern = input(colored("Patrón de exclusión (ej. test_*, *.min.js): ", Colors.CYAN)).strip() or None
    # 5. Estilo de diff
    print(colored("\nEstilo de presentación:", Colors.HEADER))
    print("1. Archivo completo (original vs modificado)")
    print("2. Diff unificado (solo líneas cambiadas)")
    print("3. Ambos")
    style_choice = input(colored("Elige (1-3) [1]: ", Colors.CYAN)).strip() or '1'
    diff_style = {'1':'full','2':'unified','3':'both'}.get(style_choice, 'full')
    # 6. Formato de salida
    print(colored("\nFormato de salida:", Colors.HEADER))
    print("1. Markdown (.md)   2. JSON (.json)   3. XML (.xml)   4. Texto (.txt)")
    print("5. HTML (.html)     6. Parche unificado (.patch)   7. Todos   8. Solo estadísticas")
    fmt_choice = input(colored("Elige (1-8) [1]: ", Colors.CYAN)).strip() or '1'
    fmt_map = {'1':'md','2':'json','3':'xml','4':'txt','5':'html','6':'patch','7':'all','8':'stats'}
    output_format = fmt_map.get(fmt_choice, 'md')
    # 7. Opciones adicionales
    compact = input(colored("Modo compacto (reducir líneas vacías)? (s/n) [n]: ", Colors.CYAN)).strip().lower() == 's'
    line_numbers = input(colored("Incluir números de línea? (s/n) [n]: ", Colors.CYAN)).strip().lower() == 's'
    preview = input(colored("Mostrar vista previa antes de exportar? (s/n) [s]: ", Colors.CYAN)).strip().lower() != 'n'
    clipboard = input(colored("Copiar informe al portapapeles? (requiere pyperclip) (s/n) [n]: ", Colors.CYAN)).strip().lower() == 's'
    # 8. Tamaño máximo de archivo (MB)
    max_size_mb = input(colored("Tamaño máximo de archivo a incluir (MB) [10]: ", Colors.CYAN)).strip() or '10'
    try:
        max_size_bytes = int(float(max_size_mb) * 1024 * 1024)
    except:
        max_size_bytes = 10 * 1024 * 1024
    # 9. Guardar perfil
    save = input(colored("¿Guardar esta configuración como perfil? (s/n) [n]: ", Colors.CYAN)).strip().lower() == 's'
    profile = {
        'ref_a': ref_a, 'ref_b': ref_b, 'subdir': subdir, 'status_filters': status_filters,
        'inc_ext': inc_ext_list, 'exc_pattern': exc_pattern, 'diff_style': diff_style,
        'output_format': output_format, 'compact': compact, 'line_numbers': line_numbers,
        'preview': preview, 'clipboard': clipboard, 'max_size_bytes': max_size_bytes
    }
    if save:
        save_profile(Path.cwd() / '.git_universal_profile.json', profile)
    return profile

# ─── Procesamiento de archivos y generación de contenido ──────────────────
def filter_changes(changes: List[Dict], status_filters: List[str], inc_ext: List[str], exc_pattern: str) -> List[Dict]:
    filtered = []
    for ch in changes:
        if ch['status'] not in status_filters:
            continue
        path = ch['path']
        # Extensión
        ext = os.path.splitext(path)[1].lower()
        if inc_ext and ext not in inc_ext:
            continue
        # Patrón exclusión
        if exc_pattern and fnmatch.fnmatch(path, exc_pattern):
            continue
        filtered.append(ch)
    return filtered

def process_file(ch: Dict, ref_a: str, ref_b: Optional[str], cache: ContentCache, diff_style: str,
                 max_size_bytes: int, compact: bool, line_numbers: bool) -> Dict:
    path = ch['path']
    file_path = Path(path)
    status = ch['status']
    original = None
    modified = None
    unified_diff = None
    size_ok = True
    if file_path.exists():
        size = file_path.stat().st_size
        if size > max_size_bytes:
            size_ok = False
    else:
        size_ok = True  # eliminado o nuevo
    # Obtener original (si existe en ref_a)
    if status != 'U' and status != 'A':
        original = cache.get_original(ref_a, path)
        if original and len(original) > max_size_bytes:
            original = f"[Archivo original demasiado grande ({format_size(len(original))}) - omitido]"
    # Obtener contenido modificado (si existe en WD)
    if status != 'D' and file_path.exists() and size_ok:
        if is_binary(file_path):
            modified = "[Archivo binario - contenido omitido]"
        else:
            modified = get_current_content(file_path)
            if modified and len(modified) > max_size_bytes:
                modified = f"[Archivo modificado demasiado grande ({format_size(len(modified))}) - omitido]"
    elif status == 'D':
        modified = None
    elif not size_ok:
        modified = f"[Archivo excede tamaño máximo ({format_size(size)}) - omitido]"
    else:
        modified = None
    # Diff unificado si se solicita
    if diff_style in ('unified', 'both') and status in ('M', 'A', 'D', 'R'):
        if ref_b is None:
            unified_diff = get_unified_diff(ref_a, None, path)
        else:
            unified_diff = get_unified_diff(ref_a, ref_b, path)
    # Aplicar compactación y números de línea solo si se pide y no es diff unificado
    if compact and original and diff_style != 'unified':
        original = '\n'.join([line for line in original.splitlines() if line.strip() != ''] or [''])
        if modified:
            modified = '\n'.join([line for line in modified.splitlines() if line.strip() != ''] or [''])
    if line_numbers and original and diff_style != 'unified':
        lines = original.splitlines()
        original = '\n'.join(f"{i+1:4d}: {line}" for i, line in enumerate(lines))
        if modified:
            lines_m = modified.splitlines()
            modified = '\n'.join(f"{i+1:4d}: {line}" for i, line in enumerate(lines_m))
    return {
        'path': path, 'status': status, 'language': get_language(os.path.splitext(path)[1], path),
        'original': original, 'modified': modified, 'unified_diff': unified_diff,
        'has_binary': (modified is not None and modified.startswith("[Archivo binario"))
    }

# ─── Generación de salidas (MD, JSON, XML, TXT, HTML, PATCH) ──────────────
def escape_html(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def generate_markdown(files_data: List[Dict], metadata: Dict, diff_style: str, compact: bool, line_numbers: bool) -> str:
    lines = ["# DIFERENCIAS GIT UNIVERSAL\n"]
    lines.append(f"**Generado:** {metadata['generated']}  \n")
    lines.append(f"**Repositorio:** {metadata['root']}  \n")
    lines.append(f"**Rama:** {metadata['branch']}  \n")
    lines.append(f"**Último commit:** {metadata['last_commit']['hash'][:7]} - {metadata['last_commit']['subject']}  \n")
    lines.append(f"**Comparación:** {metadata['ref_a']} → {metadata['ref_b'] or 'Working Directory'}  \n\n")
    lines.append("## Archivos procesados\n\n")
    for d in files_data:
        status_text = {'M':'Modificado','A':'Agregado','D':'Eliminado','U':'Untracked','R':'Renombrado'}.get(d['status'], d['status'])
        lines.append(f"### `{d['path']}` ({d['language']}) - {status_text}\n")
        if diff_style in ('full', 'both'):
            lines.append("#### Versión ORIGINAL\n```\n")
            lines.append(d['original'] if d['original'] else "[No existe en HEAD]\n")
            lines.append("\n```\n#### Versión MODIFICADA\n```\n")
            lines.append(d['modified'] if d['modified'] else "[No existe en WD]\n")
            lines.append("\n```\n")
        if diff_style in ('unified', 'both') and d.get('unified_diff'):
            lines.append("#### Diff unificado\n```diff\n")
            lines.append(d['unified_diff'])
            lines.append("\n```\n")
        lines.append("---\n\n")
    return ''.join(lines)

def generate_json(files_data: List[Dict], metadata: Dict) -> str:
    out = {'metadata': metadata, 'files': files_data}
    return json.dumps(out, indent=2, ensure_ascii=False)

def generate_xml(files_data: List[Dict], metadata: Dict) -> str:
    root = ET.Element('git_diff')
    meta = ET.SubElement(root, 'metadata')
    for k, v in metadata.items():
        if k == 'last_commit':
            lc = ET.SubElement(meta, 'last_commit')
            for lk, lv in v.items():
                ET.SubElement(lc, lk).text = str(lv)
        else:
            ET.SubElement(meta, k).text = str(v)
    files_el = ET.SubElement(root, 'files')
    for d in files_data:
        fe = ET.SubElement(files_el, 'file')
        for k, v in d.items():
            if v is not None:
                ET.SubElement(fe, k).text = str(v)
    return ET.tostring(root, encoding='unicode', xml_declaration=True)

def generate_txt(files_data: List[Dict], metadata: Dict, diff_style: str) -> str:
    lines = [f"GIT DIFF UNIVERSAL\nGenerado: {metadata['generated']}\nRepositorio: {metadata['root']}\nRama: {metadata['branch']}\n"]
    for d in files_data:
        lines.append(f"\n{'='*60}\nARCHIVO: {d['path']} ({d['language']})\n")
        if diff_style in ('full','both'):
            lines.append("ORIGINAL:\n")
            lines.append(d['original'] if d['original'] else "[No existe]")
            lines.append("\nMODIFICADO:\n")
            lines.append(d['modified'] if d['modified'] else "[No existe]")
        if diff_style in ('unified','both') and d.get('unified_diff'):
            lines.append("\nDIFF:\n")
            lines.append(d['unified_diff'])
    return ''.join(lines)

def generate_html(files_data: List[Dict], metadata: Dict, diff_style: str) -> str:
    css = HtmlFormatter().get_style_defs('.highlight') if HAS_PYGMENTS else ""
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Git Diff Universal</title>
<style>body{{font-family:sans-serif; margin:2em;}} pre{{background:#f4f4f4; padding:1em; overflow:auto;}} .file{{border-bottom:1px solid #ccc; margin-bottom:2em;}} {css}</style>
</head><body><h1>Diferencias Git</h1>
<p>Generado: {metadata['generated']}<br>Repositorio: {metadata['root']}<br>Rama: {metadata['branch']}<br>Comparación: {metadata['ref_a']} → {metadata['ref_b'] or 'WD'}</p>
"""
    for d in files_data:
        html += f"<div class='file'><h2>{d['path']} ({d['language']}) - {d['status']}</h2>"
        if diff_style in ('full','both'):
            html += "<h3>Original</h3><pre>"
            if d['original']:
                if HAS_PYGMENTS:
                    lexer = get_lexer_by_name(d['language'].lower(), startinline=True)
                    html += highlight(d['original'], lexer, HtmlFormatter())
                else:
                    html += escape_html(d['original'])
            else:
                html += "[No existe]"
            html += "</pre><h3>Modificado</h3><pre>"
            if d['modified']:
                if HAS_PYGMENTS:
                    lexer = get_lexer_by_name(d['language'].lower(), startinline=True)
                    html += highlight(d['modified'], lexer, HtmlFormatter())
                else:
                    html += escape_html(d['modified'])
            else:
                html += "[No existe]"
            html += "</pre>"
        if diff_style in ('unified','both') and d.get('unified_diff'):
            html += "<h3>Diff unificado</h3><pre>" + escape_html(d['unified_diff']) + "</pre>"
        html += "</div>"
    html += "</body></html>"
    return html

def generate_patch(files_data: List[Dict]) -> str:
    """Genera un parche unificado con todos los diffs."""
    patch_lines = []
    for d in files_data:
        if d.get('unified_diff'):
            patch_lines.append(d['unified_diff'])
    return '\n'.join(patch_lines)

def generate_stats(files_data: List[Dict]) -> Dict:
    total_files = len(files_data)
    added_lines = 0
    deleted_lines = 0
    lang_counts = {}
    for d in files_data:
        lang = d['language']
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
        if d.get('unified_diff'):
            # Parsear líneas +/-
            for line in d['unified_diff'].splitlines():
                if line.startswith('+') and not line.startswith('+++'):
                    added_lines += 1
                elif line.startswith('-') and not line.startswith('---'):
                    deleted_lines += 1
    return {
        'total_files': total_files,
        'added_lines': added_lines,
        'deleted_lines': deleted_lines,
        'languages': lang_counts
    }

# ─── Modo watch (experimental) ────────────────────────────────────────────
class ChangeHandler(FileSystemEventHandler):
    def __init__(self, callback):
        self.callback = callback
    def on_modified(self, event):
        if not event.is_directory:
            self.callback()
    def on_created(self, event):
        if not event.is_directory:
            self.callback()

def watch_mode(config: Dict):
    if not HAS_WATCHDOG:
        print(colored("Modo watch requiere watchdog: pip install watchdog", Colors.WARNING))
        return
    print(colored("Modo watch activado. Regenerará informe al detectar cambios. Ctrl+C para salir.", Colors.CYAN))
    def regenerate():
        print(colored("Cambios detectados, regenerando...", Colors.GREEN))
        run_main(config, interactive=False)  # reutilizar lógica
    handler = ChangeHandler(regenerate)
    observer = Observer()
    observer.schedule(handler, path='.', recursive=True)
    observer.start()
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

# ─── Función principal (puede ser llamada interactiva o con argumentos CLI) ─
def run_main(config: Dict = None, interactive: bool = True):
    if interactive:
        # Cargar perfil anterior si existe
        profile_path = Path.cwd() / '.git_universal_profile.json'
        profile = load_profile(profile_path)
        if profile and input(colored("¿Cargar perfil anterior? (s/n) [s]: ", Colors.CYAN)).strip().lower() != 'n':
            config = profile
        else:
            config = interactive_menu(profile)
    # Si se pasó config por CLI, usarlo
    ref_a = config['ref_a']
    ref_b = config.get('ref_b')
    subdir = config.get('subdir', '.')
    status_filters = config.get('status_filters', ['M','A','D','U','R','C'])
    inc_ext = config.get('inc_ext', [])
    exc_pattern = config.get('exc_pattern')
    diff_style = config.get('diff_style', 'full')
    output_format = config.get('output_format', 'md')
    compact = config.get('compact', False)
    line_numbers = config.get('line_numbers', False)
    preview = config.get('preview', True)
    clipboard = config.get('clipboard', False)
    max_size_bytes = config.get('max_size_bytes', 10*1024*1024)
    # Obtener cambios
    all_changes = get_all_changes(ref_a, ref_b, subdir)
    if not all_changes:
        print(colored("No se encontraron cambios.", Colors.GREEN))
        return
    # Aplicar filtros
    filtered = filter_changes(all_changes, status_filters, inc_ext, exc_pattern)
    if not filtered:
        print(colored("No hay archivos que cumplan los filtros.", Colors.WARNING))
        return
    print(colored(f"Procesando {len(filtered)} archivos...", Colors.CYAN))
    # Cache y procesamiento en paralelo
    cache = ContentCache()
    files_data = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(process_file, ch, ref_a, ref_b, cache, diff_style, max_size_bytes, compact, line_numbers): ch for ch in filtered}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Procesando") if HAS_TQDM else as_completed(futures):
            files_data.append(future.result())
    # Metadatos
    repo_root = get_git_repo_root()
    metadata = {
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'system': platform.platform(),
        'user': getpass.getuser(),
        'root': str(repo_root),
        'branch': get_current_branch(),
        'last_commit': get_last_commit(),
        'ref_a': ref_a, 'ref_b': ref_b or 'Working Directory'
    }
    # Vista previa
    if preview:
        print(colored("\n=== VISTA PREVIA ===", Colors.BOLD))
        print(f"Archivos a incluir: {len(files_data)}")
        print(f"Estilo diff: {diff_style}")
        print(f"Formato salida: {output_format}")
        print(f"Compacto: {compact}, Líneas numeradas: {line_numbers}")
        confirm = input(colored("¿Continuar? (s/n) [s]: ", Colors.CYAN)).strip().lower()
        if confirm == 'n':
            print("Cancelado.")
            return
    # Generar contenido según formato
    output_dir = Path.cwd() / 'git_universal_output'
    output_dir.mkdir(exist_ok=True)
    # Calcular siguiente versión
    max_v = 0
    for f in output_dir.glob(f"git_universal_*.{output_format if output_format!='all' else '*'}") :
        try:
            num = int(f.stem.split('_')[-1])
            max_v = max(max_v, num)
        except: pass
    version = max_v + 1
    out_files = []
    if output_format == 'all':
        for fmt in ['md', 'json', 'xml', 'txt', 'html', 'patch']:
            out_file = output_dir / f'git_universal_{version:03d}.{fmt}'
            content = globals()[f'generate_{fmt}'](files_data, metadata, diff_style) if fmt != 'patch' else generate_patch(files_data)
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write(content)
            out_files.append(str(out_file))
    else:
        out_file = output_dir / f'git_universal_{version:03d}.{output_format}'
        if output_format == 'patch':
            content = generate_patch(files_data)
        else:
            generate_func = globals()[f'generate_{output_format}']
            content = generate_func(files_data, metadata, diff_style)
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write(content)
        out_files.append(str(out_file))
    # Estadísticas
    stats = generate_stats(files_data)
    print(colored("\n=== ESTADÍSTICAS ===", Colors.BOLD))
    print(f"Archivos: {stats['total_files']}  |  Líneas +{stats['added_lines']} / -{stats['deleted_lines']}")
    print(f"Lenguajes: {', '.join(f'{k}({v})' for k,v in stats['languages'].items())}")
    print(colored(f"Archivos generados: {', '.join(out_files)}", Colors.GREEN))
    # Copiar al portapapeles si se pide
    if clipboard and HAS_CLIPBOARD:
        try:
            with open(out_files[0], 'r', encoding='utf-8') as f:
                pyperclip.copy(f.read())
            print(colored("Contenido copiado al portapapeles.", Colors.GREEN))
        except:
            print(colored("No se pudo copiar al portapapeles.", Colors.WARNING))

def main():
    parser = argparse.ArgumentParser(description="Generador universal de diferencias Git")
    parser.add_argument('--watch', action='store_true', help='Modo watch (regenera automáticamente)')
    parser.add_argument('--config', type=Path, help='Cargar configuración desde archivo JSON')
    args = parser.parse_args()
    if args.watch:
        # Cargar perfil existente o crear uno por defecto
        profile_path = Path.cwd() / '.git_universal_profile.json'
        config = load_profile(profile_path)
        if not config:
            config = interactive_menu(None)
            save_profile(profile_path, config)
        watch_mode(config)
    else:
        run_main(interactive=True)

if __name__ == '__main__':
    main()