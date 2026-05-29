#!/usr/bin/env python3
"""
Generador universal de diferencias Git (todas las mejoras integradas)
Funciona sin dependencias externas; las opcionales mejoran la experiencia.
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
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional

# ─── Dependencias opcionales (todo con try/except) ────────────────────────
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
    from pygments.lexers import get_lexer_by_name
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
    ENDC = '\033[0m'; BOLD = '\033[1m'

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
            return b'\0' in f.read(8192)
    except:
        return True

def get_language(ext: str, filename: str = '') -> str:
    lang_map = {
        '.py':'Python','.js':'JavaScript','.ts':'TypeScript','.java':'Java',
        '.c':'C','.cpp':'C++','.go':'Go','.rs':'Rust','.md':'Markdown',
        '.json':'JSON','.xml':'XML','.yaml':'YAML','.sh':'Bash',
        '.html':'HTML','.css':'CSS','.sql':'SQL','.txt':'Text'
    }
    return lang_map.get(ext.lower(), 'Texto')

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
        out = subprocess.check_output(['git', 'log', '-1', '--format=%H%n%s%n%an%n%ae%n%ad'], text=True).strip().splitlines()
        return {'hash': out[0], 'subject': out[1], 'author': out[2], 'email': out[3], 'date': out[4]}
    except:
        return {}

# ─── Filtros .contextignore ────────────────────────────────────────────────
def load_contextignore(start_path: Path = None) -> List[str]:
    if start_path is None:
        start_path = Path.cwd()
    ignore_file = start_path / '.contextignore'
    if not ignore_file.exists():
        default = ['__pycache__/', 'node_modules/', 'dist/', 'build/', '.git/', '.idea/']
        with open(ignore_file, 'w') as f:
            f.write('\n'.join(default) + '\n')
        return default
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

# ─── Obtención de cambios Git ──────────────────────────────────────────────
def get_all_changes(ref_a: str = 'HEAD', ref_b: str = None, subdir: str = '.') -> List[Dict]:
    if ref_b is None:
        try:
            output = subprocess.check_output(['git', 'status', '--porcelain', '--', subdir], text=True, stderr=subprocess.DEVNULL)
        except:
            return []
    else:
        try:
            output = subprocess.check_output(['git', 'diff', '--name-status', f'{ref_a}..{ref_b}', '--', subdir], text=True, stderr=subprocess.DEVNULL)
            changes = []
            for line in output.strip().splitlines():
                if not line:
                    continue
                parts = line.split(maxsplit=1)
                if len(parts) != 2:
                    continue
                status, path = parts[0], parts[1]
                changes.append({'path': path, 'status': status[0]})
            return changes
        except:
            return []
    changes = []
    for line in output.strip().splitlines():
        if not line:
            continue
        code = line[:2]
        rest = line[3:].strip()
        x, y = code[0], code[1]
        if y == 'M' or x == 'M':
            final = 'M'
        elif y == 'D' or x == 'D':
            final = 'D'
        elif y == 'A' or x == 'A':
            final = 'A'
        elif y == 'R' or x == 'R':
            final = 'R'
            if ' -> ' in rest:
                new = rest.split(' -> ')[1]
                changes.append({'path': new, 'status': final, 'old_path': rest.split(' -> ')[0]})
                continue
        elif y == '?' and x == '?':
            final = 'U'
        else:
            continue
        changes.append({'path': rest, 'status': final})
    return changes

def get_original_content(ref: str, path: str) -> Optional[str]:
    try:
        return subprocess.check_output(['git', 'show', f'{ref}:{path}'], text=True, stderr=subprocess.DEVNULL)
    except:
        return None

def get_current_content(filepath: Path) -> Optional[str]:
    if not filepath.exists():
        return None
    if is_binary(filepath):
        return None
    enc = detect_encoding(filepath)
    try:
        with open(filepath, 'r', encoding=enc, errors='replace') as f:
            return f.read()
    except:
        return None

def get_unified_diff(ref_a: str, ref_b: Optional[str], filepath: str, context: int = 3) -> str:
    if ref_b is None:
        cmd = ['git', 'diff', f'-U{context}', ref_a, '--', filepath]
    else:
        cmd = ['git', 'diff', f'-U{context}', f'{ref_a}..{ref_b}', '--', filepath]
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
    except:
        return "[No se pudo generar diff]"

# ─── Cache ─────────────────────────────────────────────────────────────────
class ContentCache:
    def __init__(self):
        self._cache = {}
    def get(self, ref: str, path: str) -> Optional[str]:
        key = f"{ref}:{path}"
        if key not in self._cache:
            self._cache[key] = get_original_content(ref, path)
        return self._cache[key]

# ─── Menú interactivo y perfil ─────────────────────────────────────────────
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
    print(colored("\n=== CONFIGURACIÓN DEL INFORME ===", Colors.BOLD))
    if profile and 'ref_a' in profile:
        ref_a = profile['ref_a']
        ref_b = profile.get('ref_b')
        print(colored(f"Referencias cargadas: {ref_a} → {ref_b if ref_b else 'WD'}", Colors.GREEN))
    else:
        ref_a = input(colored("Referencia base (commit, tag, rama) [HEAD]: ", Colors.CYAN)).strip() or 'HEAD'
        ref_b = input(colored("Referencia destino (vacío para Working Directory): ", Colors.CYAN)).strip() or None
    subdir = input(colored("Subdirectorio (vacío para raíz): ", Colors.CYAN)).strip() or '.'
    print(colored("\nFiltrar por tipo (M,A,D,U,R,C o all):", Colors.HEADER))
    status_choice = input(colored("Selección [all]: ", Colors.CYAN)).strip().lower() or 'all'
    if status_choice == 'all':
        status_filters = ['M','A','D','U','R','C']
    else:
        status_filters = [s.upper() for s in status_choice.split(',') if s.upper() in 'MADURC']
    inc_ext = input(colored("Extensiones a incluir (ej. .py,.md): ", Colors.CYAN)).strip()
    inc_ext_list = [e.lower() for e in inc_ext.split(',')] if inc_ext else []
    exc_pattern = input(colored("Patrón exclusión (ej. test_*): ", Colors.CYAN)).strip() or None
    print(colored("\nEstilo de diff:", Colors.HEADER))
    print("1. Archivo completo (original vs modificado)")
    print("2. Diff unificado (solo líneas cambiadas)")
    print("3. Ambos")
    style = input(colored("Elige (1-3) [1]: ", Colors.CYAN)).strip() or '1'
    diff_style = {'1':'full','2':'unified','3':'both'}[style]
    print(colored("\nFormato de salida:", Colors.HEADER))
    print("1. Markdown  2. JSON  3. XML  4. Texto  5. HTML  6. Patch  7. Todos  8. Solo estadísticas")
    fmt = input(colored("Elige (1-8) [1]: ", Colors.CYAN)).strip() or '1'
    fmt_map = {'1':'md','2':'json','3':'xml','4':'txt','5':'html','6':'patch','7':'all','8':'stats'}
    output_format = fmt_map[fmt]
    compact = input(colored("Modo compacto? (s/n) [n]: ", Colors.CYAN)).strip().lower() == 's'
    line_nums = input(colored("Números de línea? (s/n) [n]: ", Colors.CYAN)).strip().lower() == 's'
    preview = input(colored("Vista previa antes de exportar? (s/n) [s]: ", Colors.CYAN)).strip().lower() != 'n'
    clipboard = input(colored("Copiar al portapapeles? (requiere pyperclip) (s/n) [n]: ", Colors.CYAN)).strip().lower() == 's'
    max_mb = input(colored("Tamaño máximo de archivo (MB) [10]: ", Colors.CYAN)).strip() or '10'
    max_bytes = int(float(max_mb) * 1024 * 1024)
    save = input(colored("¿Guardar perfil? (s/n) [n]: ", Colors.CYAN)).strip().lower() == 's'
    profile_data = {
        'ref_a': ref_a, 'ref_b': ref_b, 'subdir': subdir, 'status_filters': status_filters,
        'inc_ext': inc_ext_list, 'exc_pattern': exc_pattern, 'diff_style': diff_style,
        'output_format': output_format, 'compact': compact, 'line_numbers': line_nums,
        'preview': preview, 'clipboard': clipboard, 'max_size_bytes': max_bytes
    }
    if save:
        save_profile(Path.cwd() / '.git_universal_profile.json', profile_data)
    return profile_data

# ─── Generación de salidas ─────────────────────────────────────────────────
def escape_html(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def generate_markdown(files_data: List[Dict], metadata: Dict, diff_style: str) -> str:
    lines = ["# DIFERENCIAS GIT\n\n"]
    lines.append(f"**Generado:** {metadata['generated']}  \n")
    lines.append(f"**Repositorio:** {metadata['root']}  \n")
    lines.append(f"**Rama:** {metadata['branch']}  \n")
    lines.append(f"**Último commit:** {metadata['last_commit'].get('hash','')[:7]} - {metadata['last_commit'].get('subject','')}  \n")
    lines.append(f"**Comparación:** {metadata['ref_a']} → {metadata['ref_b'] or 'WD'}  \n\n")
    for d in files_data:
        status_text = {'M':'Modificado','A':'Agregado','D':'Eliminado','U':'Untracked','R':'Renombrado'}.get(d['status'], d['status'])
        lines.append(f"### `{d['path']}` ({d['language']}) - {status_text}\n")
        if diff_style in ('full','both'):
            lines.append("#### Original\n```\n")
            lines.append(d['original'] if d['original'] else "[No existe]\n")
            lines.append("\n```\n#### Modificado\n```\n")
            lines.append(d['modified'] if d['modified'] else "[No existe]\n")
            lines.append("\n```\n")
        if diff_style in ('unified','both') and d.get('unified_diff'):
            lines.append("#### Diff unificado\n```diff\n")
            lines.append(d['unified_diff'])
            lines.append("\n```\n")
        lines.append("---\n\n")
    return ''.join(lines)

def generate_json(files_data: List[Dict], metadata: Dict, _=None) -> str:
    return json.dumps({'metadata': metadata, 'files': files_data}, indent=2, ensure_ascii=False)

def generate_xml(files_data: List[Dict], metadata: Dict, _=None) -> str:
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
    lines = [f"GIT DIFF\nGenerado: {metadata['generated']}\nRepositorio: {metadata['root']}\nRama: {metadata['branch']}\n"]
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
    css = ""
    if HAS_PYGMENTS:
        css = HtmlFormatter().get_style_defs('.highlight')
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Git Diff</title>
<style>body{{font-family:sans-serif;margin:2em;}}pre{{background:#f4f4f4;padding:1em;overflow:auto;}}.file{{border-bottom:1px solid #ccc;margin-bottom:2em;}}{css}</style>
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

def generate_patch(files_data: List[Dict], _=None, __=None) -> str:
    return '\n'.join(d.get('unified_diff', '') for d in files_data if d.get('unified_diff'))

def generate_stats(files_data: List[Dict], metadata: Dict, _=None) -> str:
    total = len(files_data)
    added = 0
    deleted = 0
    langs = {}
    for d in files_data:
        langs[d['language']] = langs.get(d['language'], 0) + 1
        if d.get('unified_diff'):
            for line in d['unified_diff'].splitlines():
                if line.startswith('+') and not line.startswith('+++'):
                    added += 1
                elif line.startswith('-') and not line.startswith('---'):
                    deleted += 1
    out = f"Total archivos: {total}\nLíneas +{added} / -{deleted}\nLenguajes: " + ', '.join(f"{k}({v})" for k,v in langs.items())
    return out

# ─── Procesamiento de archivos ─────────────────────────────────────────────
def process_file(ch: Dict, ref_a: str, ref_b: Optional[str], cache: ContentCache,
                 diff_style: str, max_bytes: int, compact: bool, line_nums: bool) -> Dict:
    path = ch['path']
    file_path = Path(path)
    status = ch['status']
    original = None
    modified = None
    unified = None
    if status not in ('U','A'):
        original = cache.get(ref_a, path)
        if original and len(original) > max_bytes:
            original = f"[Archivo original demasiado grande ({format_size(len(original))})]"
    if status != 'D' and file_path.exists():
        sz = file_path.stat().st_size
        if sz > max_bytes:
            modified = f"[Archivo excede {format_size(max_bytes)}]"
        else:
            if is_binary(file_path):
                modified = "[Archivo binario - contenido omitido]"
            else:
                modified = get_current_content(file_path)
    if diff_style in ('unified','both') and status in ('M','A','D','R'):
        unified = get_unified_diff(ref_a, ref_b, path)
    if compact:
        if original:
            original = '\n'.join([l for l in original.splitlines() if l.strip()!=''] or [''])
        if modified:
            modified = '\n'.join([l for l in modified.splitlines() if l.strip()!=''] or [''])
    if line_nums and original:
        lines = original.splitlines()
        original = '\n'.join(f"{i+1:4d}: {l}" for i,l in enumerate(lines))
        if modified:
            lines_m = modified.splitlines()
            modified = '\n'.join(f"{i+1:4d}: {l}" for i,l in enumerate(lines_m))
    return {
        'path': path, 'status': status, 'language': get_language(os.path.splitext(path)[1], path),
        'original': original, 'modified': modified, 'unified_diff': unified
    }

# ─── Modo watch (solo si watchdog está instalado) ─────────────────────────
if HAS_WATCHDOG:
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
        print(colored("Modo watch activado. Regenerará al detectar cambios. Ctrl+C para salir.", Colors.CYAN))
        def regenerate():
            print(colored("Cambios detectados, regenerando...", Colors.GREEN))
            run_main(config, interactive=False)
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
else:
    def watch_mode(config):
        print(colored("Modo watch no disponible: instala watchdog (pip install watchdog)", Colors.WARNING))

# ─── Función principal ────────────────────────────────────────────────────
def run_main(config: Dict = None, interactive: bool = True):
    if interactive:
        profile_path = Path.cwd() / '.git_universal_profile.json'
        profile = load_profile(profile_path)
        if profile and input(colored("¿Cargar perfil anterior? (s/n) [s]: ", Colors.CYAN)).strip().lower() != 'n':
            config = profile
        else:
            config = interactive_menu(profile)
    ref_a = config['ref_a']
    ref_b = config.get('ref_b')
    subdir = config.get('subdir', '.')
    status_filters = config.get('status_filters', ['M','A','D','U','R','C'])
    inc_ext = config.get('inc_ext', [])
    exc_pattern = config.get('exc_pattern')
    diff_style = config.get('diff_style', 'full')
    output_format = config.get('output_format', 'md')
    compact = config.get('compact', False)
    line_nums = config.get('line_numbers', False)
    preview = config.get('preview', True)
    clipboard = config.get('clipboard', False)
    max_bytes = config.get('max_size_bytes', 10*1024*1024)

    all_changes = get_all_changes(ref_a, ref_b, subdir)
    if not all_changes:
        print(colored("No se encontraron cambios.", Colors.GREEN))
        return

    filtered = []
    for ch in all_changes:
        if ch['status'] not in status_filters:
            continue
        ext = os.path.splitext(ch['path'])[1].lower()
        if inc_ext and ext not in inc_ext:
            continue
        if exc_pattern and fnmatch.fnmatch(ch['path'], exc_pattern):
            continue
        filtered.append(ch)
    if not filtered:
        print(colored("No hay archivos que cumplan los filtros.", Colors.WARNING))
        return

    print(colored(f"Procesando {len(filtered)} archivos...", Colors.CYAN))
    cache = ContentCache()
    files_data = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(process_file, ch, ref_a, ref_b, cache, diff_style, max_bytes, compact, line_nums): ch for ch in filtered}
        if HAS_TQDM:
            for future in tqdm(as_completed(futures), total=len(futures), desc="Procesando"):
                files_data.append(future.result())
        else:
            for future in as_completed(futures):
                files_data.append(future.result())

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

    if preview:
        print(colored("\n=== VISTA PREVIA ===", Colors.BOLD))
        print(f"Archivos a incluir: {len(files_data)}")
        print(f"Estilo diff: {diff_style}")
        print(f"Formato salida: {output_format}")
        if input(colored("¿Continuar? (s/n) [s]: ", Colors.CYAN)).strip().lower() == 'n':
            return

    output_dir = Path.cwd() / 'git_universal_output'
    output_dir.mkdir(exist_ok=True)
    max_v = 0
    for f in output_dir.glob(f"git_universal_*.*"):
        try:
            num = int(f.stem.split('_')[-1])
            max_v = max(max_v, num)
        except:
            pass
    version = max_v + 1
    out_files = []
    if output_format == 'all':
        for fmt in ['md','json','xml','txt','html','patch']:
            out_file = output_dir / f'git_universal_{version:03d}.{fmt}'
            content = globals()[f'generate_{fmt}'](files_data, metadata, diff_style)
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write(content)
            out_files.append(str(out_file))
    else:
        out_file = output_dir / f'git_universal_{version:03d}.{output_format}'
        func = globals()[f'generate_{output_format}']
        content = func(files_data, metadata, diff_style)
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write(content)
        out_files.append(str(out_file))

    # Estadísticas en consola
    stats = generate_stats(files_data, metadata, None)
    print(colored("\n=== ESTADÍSTICAS ===", Colors.BOLD))
    print(stats)
    print(colored(f"Archivos generados: {', '.join(out_files)}", Colors.GREEN))

    if clipboard and HAS_CLIPBOARD:
        try:
            with open(out_files[0], 'r', encoding='utf-8') as f:
                pyperclip.copy(f.read())
            print(colored("Contenido copiado al portapapeles.", Colors.GREEN))
        except:
            print(colored("No se pudo copiar al portapapeles.", Colors.WARNING))

def main():
    parser = argparse.ArgumentParser(description="Generador universal de diferencias Git")
    parser.add_argument('--watch', action='store_true', help="Modo watch (requiere watchdog)")
    args = parser.parse_args()
    if args.watch:
        if not HAS_WATCHDOG:
            print(colored("Error: --watch requiere watchdog. Instala con: pip install watchdog", Colors.FAIL))
            sys.exit(1)
        profile_path = Path.cwd() / '.git_universal_profile.json'
        config = load_profile(profile_path)
        if not config:
            print(colored("No hay perfil guardado. Ejecuta primero sin --watch para crear uno.", Colors.WARNING))
            config = interactive_menu(None)
            save_profile(profile_path, config)
        watch_mode(config)
    else:
        run_main(interactive=True)

if __name__ == '__main__':
    main()