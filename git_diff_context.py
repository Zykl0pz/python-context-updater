#!/usr/bin/env python3
"""
Generador de diferencias Git (HEAD vs Working Directory)
Compatible con archivos nuevos, modificados y eliminados.
"""

import os
import sys
import subprocess
import json
import xml.etree.ElementTree as ET
import platform
import getpass
import fnmatch
import re
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple

# ─── Dependencias opcionales ───────────────────────────────────────────────
try:
    from charset_normalizer import from_bytes
    HAS_CHARSET = True
except ImportError:
    HAS_CHARSET = False

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

# ─── Colores ──────────────────────────────────────────────────────────────
class Colors:
    HEADER = '\033[95m'; BLUE = '\033[94m'; CYAN = '\033[96m'
    GREEN = '\033[92m'; WARNING = '\033[93m'; FAIL = '\033[91m'
    ENDC = '\033[0m'; BOLD = '\033[1m'

def colored(text: str, color: str) -> str:
    return f"{color}{text}{Colors.ENDC}" if sys.stdout.isatty() else text

# ─── Utilidades generales ─────────────────────────────────────────────────
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

def is_binary_data(data: bytes) -> bool:
    return b'\0' in data[:8192]

def is_binary_file(filepath: Path) -> bool:
    try:
        with open(filepath, 'rb') as f:
            return is_binary_data(f.read(8192))
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
        print(colored("Error: No estás dentro de un repositorio Git.", Colors.FAIL))
        sys.exit(1)

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

# ─── Fechas de modificación ──────────────────────────────────────────────
def get_local_mtime(filepath: Path) -> Optional[float]:
    if filepath.exists():
        try:
            return os.path.getmtime(filepath)
        except:
            pass
    return None

def get_head_mtime(repo_root: Path, filepath: str) -> Optional[float]:
    try:
        output = subprocess.check_output(
            ['git', 'log', '-1', '--format=%ct', 'HEAD', '--', filepath],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL
        ).strip()
        if output:
            return float(output)
    except:
        pass
    return None

def format_timestamp(ts: Optional[float]) -> str:
    if ts is None:
        return "[No disponible]"
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

# ─── Obtener cambios desde Git (con diagnóstico) ─────────────────────────
def get_all_changes(repo_root: Path) -> List[Dict]:
    try:
        # Capturamos también stderr para diagnóstico
        proc = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=repo_root,
            capture_output=True,
            text=True
        )
        if proc.returncode != 0:
            print(colored(f"Error al ejecutar git status: {proc.stderr.strip()}", Colors.FAIL))
            return []
        output = proc.stdout
        # Eliminar cualquier BOM (byte order mark) en toda la cadena
        output = output.replace('\ufeff', '')
        # Mostrar diagnóstico de la salida cruda
        if output.strip():
            print(colored("[DIAGNÓSTICO] Salida de git status --porcelain:", Colors.CYAN))
            for line in output.strip().splitlines():
                print(f"  {repr(line)}")
    except Exception as e:
        print(colored(f"Excepción al ejecutar git status: {e}", Colors.FAIL))
        return []
    changes = []
    for line in output.strip().splitlines():
        if not line:
            continue
        # Regex para extraer los dos primeros caracteres (estado) y la ruta,
        # aceptando cualquier espacio/tabulador como separador
        match = re.match(r'^(.{2})\s+(.*?)\s*$', line)
        if not match:
            print(colored(f"[DIAGNÓSTICO] Línea ignorada (formato no reconocido): {repr(line)}", Colors.WARNING))
            continue
        code = match.group(1)
        rest = match.group(2).strip()
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
            final = None
        if final:
            changes.append({'path': rest, 'status': final})
    print(colored(f"[DIAGNÓSTICO] Cambios detectados por el script: {[(c['path'], c['status']) for c in changes]}", Colors.CYAN))
    return changes

def get_original_content(repo_root: Path, path: str) -> Optional[str]:
    """Devuelve el contenido del archivo en HEAD, o None si no existe o es binario."""
    try:
        data = subprocess.check_output(
            ['git', 'show', f'HEAD:{path}'],
            cwd=repo_root,
            stderr=subprocess.DEVNULL
        )
        if is_binary_data(data):
            return None
        return data.decode('utf-8', errors='replace')
    except:
        return None

def get_current_content(filepath: Path) -> Optional[str]:
    if not filepath.exists():
        return None
    if is_binary_file(filepath):
        return None
    enc = detect_encoding(filepath)
    try:
        with open(filepath, 'r', encoding=enc, errors='replace') as f:
            return f.read()
    except:
        return None

def get_unified_diff(repo_root: Path, filepath: str, context: int = 3) -> str:
    try:
        return subprocess.check_output(
            ['git', 'diff', f'-U{context}', 'HEAD', '--', filepath],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL
        )
    except:
        return "[No se pudo generar diff]"

# ─── Filtros .contextignore ──────────────────────────────────────────────
def load_contextignore(repo_root: Path) -> List[str]:
    ignore_file = repo_root / '.contextignore'
    if not ignore_file.exists():
        default = ['__pycache__/', 'node_modules/', 'dist/', 'build/', '.git/', '.idea/']
        # No lo creamos automáticamente para evitar confusiones, solo usamos la lista por defecto
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

# ─── Menú interactivo y perfil ───────────────────────────────────────────
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

def interactive_menu() -> Dict:
    print(colored("\n=== CONFIGURACIÓN DEL INFORME ===", Colors.BOLD))
    print(colored("\nFiltrar por tipo de cambio (M,A,D,U,R,C o all):", Colors.HEADER))
    status_choice = input(colored("Selección [all]: ", Colors.CYAN)).strip().lower() or 'all'
    if status_choice == 'all':
        status_filters = ['M','A','D','U','R','C']
    else:
        status_filters = [s.upper() for s in status_choice.split(',') if s.upper() in 'MADURC']
    inc_ext = input(colored("Extensiones a incluir (ej. .py,.md) [vacío = todas]: ", Colors.CYAN)).strip()
    inc_ext_list = [e.lower() for e in inc_ext.split(',')] if inc_ext else []
    exc_pattern = input(colored("Patrón de exclusión (ej. test_*): ", Colors.CYAN)).strip() or None
    print(colored("\nEstilo de presentación:", Colors.HEADER))
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
    compact = input(colored("Modo compacto (reducir líneas vacías)? (s/n) [n]: ", Colors.CYAN)).strip().lower() == 's'
    line_nums = False
    if output_format in ('md', 'all'):
        line_nums = input(colored("Incluir números de línea? (s/n) [n]: ", Colors.CYAN)).strip().lower() == 's'
    show_dates = input(colored("¿Mostrar fechas de modificación (local y en HEAD)? (s/n) [s]: ", Colors.CYAN)).strip().lower() != 'n'
    sort_by_date = True
    if show_dates:
        sort_by_date = input(colored("¿Ordenar archivos por fecha de modificación local (más reciente primero)? (s/n) [s]: ", Colors.CYAN)).strip().lower() != 'n'
    preview = input(colored("Vista previa antes de exportar? (s/n) [n]: ", Colors.CYAN)).strip().lower() == 's'
    clipboard = input(colored("Copiar al portapapeles? (requiere pyperclip) (s/n) [n]: ", Colors.CYAN)).strip().lower() == 's'
    save = input(colored("¿Guardar esta configuración como perfil? (s/n) [n]: ", Colors.CYAN)).strip().lower() == 's'
    config = {
        'status_filters': status_filters,
        'inc_ext': inc_ext_list,
        'exc_pattern': exc_pattern,
        'diff_style': diff_style,
        'output_format': output_format,
        'compact': compact,
        'line_numbers': line_nums,
        'show_dates': show_dates,
        'sort_by_date': sort_by_date,
        'preview': preview,
        'clipboard': clipboard
    }
    if save:
        save_profile(Path.cwd() / '.git_diff_simple_profile.json', config)
    return config

# ─── Generación de salidas (todas las funciones necesarias) ──────────────
def escape_html(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def generate_markdown(files_data: List[Dict], metadata: Dict, diff_style: str = 'full', show_dates: bool = False) -> str:
    lines = ["# DIFERENCIAS GIT (HEAD vs Working Directory)\n\n"]
    lines.append(f"**Generado:** {metadata['generated']}  \n")
    lines.append(f"**Repositorio:** {metadata['root']}  \n")
    lines.append(f"**Rama:** {metadata['branch']}  \n")
    lines.append(f"**Último commit:** {metadata['last_commit'].get('hash','')[:7]} - {metadata['last_commit'].get('subject','')}  \n\n")
    for d in files_data:
        status_text = {'M':'Modificado','A':'Agregado','D':'Eliminado','U':'Untracked','R':'Renombrado'}.get(d['status'], d['status'])
        lines.append(f"### `{d['path']}` ({d['language']}) - {status_text}\n")
        if show_dates:
            local = format_timestamp(d.get('local_mtime'))
            head = format_timestamp(d.get('head_mtime'))
            lines.append(f"- **Fecha modificación local:** {local}  \n")
            lines.append(f"- **Fecha en HEAD:** {head}  \n\n")
        if diff_style in ('full','both'):
            lines.append("#### Original\n```\n")
            if d['original'] is None:
                lines.append("[Archivo no existe en HEAD (nuevo o binario)]\n")
            elif d['original'] == "":
                lines.append("[Archivo vacío en HEAD]\n")
            else:
                lines.append(d['original'])
            lines.append("\n```\n#### Modificado\n```\n")
            if d['modified'] is None:
                lines.append("[Archivo no existe en WD (eliminado o binario)]\n")
            elif d['modified'] == "":
                lines.append("[Archivo vacío en WD]\n")
            else:
                lines.append(d['modified'])
            lines.append("\n```\n")
        if diff_style in ('unified','both') and d.get('unified_diff'):
            lines.append("#### Diff unificado\n```diff\n")
            lines.append(d['unified_diff'])
            lines.append("\n```\n")
        lines.append("---\n\n")
    return ''.join(lines)

def generate_json(files_data: List[Dict], metadata: Dict, diff_style: str = None, show_dates: bool = None) -> str:
    return json.dumps({'metadata': metadata, 'files': files_data}, indent=2, ensure_ascii=False)

def generate_xml(files_data: List[Dict], metadata: Dict, diff_style: str = None, show_dates: bool = None) -> str:
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

def generate_txt(files_data: List[Dict], metadata: Dict, diff_style: str = 'full', show_dates: bool = False) -> str:
    lines = [f"GIT DIFF\nGenerado: {metadata['generated']}\nRepositorio: {metadata['root']}\nRama: {metadata['branch']}\n"]
    for d in files_data:
        lines.append(f"\n{'='*60}\nARCHIVO: {d['path']} ({d['language']})\n")
        if show_dates:
            local = format_timestamp(d.get('local_mtime'))
            head = format_timestamp(d.get('head_mtime'))
            lines.append(f"Fecha modificación local: {local}\nFecha en HEAD: {head}\n")
        if diff_style in ('full','both'):
            lines.append("ORIGINAL:\n")
            if d['original'] is None:
                lines.append("[No existe en HEAD]\n")
            elif d['original'] == "":
                lines.append("[Vacío]\n")
            else:
                lines.append(d['original'])
            lines.append("\nMODIFICADO:\n")
            if d['modified'] is None:
                lines.append("[No existe en WD]\n")
            elif d['modified'] == "":
                lines.append("[Vacío]\n")
            else:
                lines.append(d['modified'])
        if diff_style in ('unified','both') and d.get('unified_diff'):
            lines.append("\nDIFF:\n")
            lines.append(d['unified_diff'])
    return ''.join(lines)

def generate_html(files_data: List[Dict], metadata: Dict, diff_style: str = 'full', show_dates: bool = False) -> str:
    css = ""
    if HAS_PYGMENTS:
        css = HtmlFormatter().get_style_defs('.highlight')
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Git Diff</title>
<style>body{{font-family:sans-serif;margin:2em;}}pre{{background:#f4f4f4;padding:1em;overflow:auto;}}.file{{border-bottom:1px solid #ccc;margin-bottom:2em;}}{css}</style>
</head><body><h1>Diferencias Git</h1>
<p>Generado: {metadata['generated']}<br>Repositorio: {metadata['root']}<br>Rama: {metadata['branch']}</p>
"""
    for d in files_data:
        html += f"<div class='file'><h2>{d['path']} ({d['language']}) - {d['status']}</h2>"
        if show_dates:
            local = format_timestamp(d.get('local_mtime'))
            head = format_timestamp(d.get('head_mtime'))
            html += f"<p><strong>Modificación local:</strong> {local}<br><strong>Modificación en HEAD:</strong> {head}</p>"
        if diff_style in ('full','both'):
            html += "<h3>Original</h3><pre>"
            if d['original'] is None:
                html += "[No existe en HEAD]"
            elif d['original'] == "":
                html += "[Vacío]"
            else:
                if HAS_PYGMENTS:
                    lexer = get_lexer_by_name(d['language'].lower(), startinline=True)
                    html += highlight(d['original'], lexer, HtmlFormatter())
                else:
                    html += escape_html(d['original'])
            html += "</pre><h3>Modificado</h3><pre>"
            if d['modified'] is None:
                html += "[No existe en WD]"
            elif d['modified'] == "":
                html += "[Vacío]"
            else:
                if HAS_PYGMENTS:
                    lexer = get_lexer_by_name(d['language'].lower(), startinline=True)
                    html += highlight(d['modified'], lexer, HtmlFormatter())
                else:
                    html += escape_html(d['modified'])
            html += "</pre>"
        if diff_style in ('unified','both') and d.get('unified_diff'):
            html += "<h3>Diff unificado</h3><pre>" + escape_html(d['unified_diff']) + "</pre>"
        html += "</div>"
    html += "</body></html>"
    return html

def generate_patch(files_data: List[Dict], metadata: Dict = None, diff_style: str = None, show_dates: bool = None) -> str:
    patches = [d.get('unified_diff', '') for d in files_data if d.get('unified_diff')]
    return '\n'.join(patches)

def generate_stats(files_data: List[Dict], metadata: Dict = None, diff_style: str = None, show_dates: bool = None) -> str:
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

# ─── Procesamiento de archivos (robusto) ─────────────────────────────────
def process_file(ch: Dict, repo_root: Path, diff_style: str, compact: bool, line_nums: bool) -> Dict:
    path = ch['path']
    file_path = repo_root / path
    status = ch['status']
    original = None
    modified = None
    unified = None

    # Fechas
    local_mtime = get_local_mtime(file_path) if file_path.exists() else None
    head_mtime = get_head_mtime(repo_root, path) if status not in ('U','A') else None

    # Contenido original (solo si existe en HEAD)
    if status not in ('U', 'A'):
        original = get_original_content(repo_root, path)

    # Contenido modificado (si el archivo existe en WD)
    if status != 'D' and file_path.exists():
        if is_binary_file(file_path):
            modified = None
        else:
            modified = get_current_content(file_path)
    else:
        modified = None

    # Diff unificado
    if diff_style in ('unified','both') and status in ('M','A','D','R'):
        unified = get_unified_diff(repo_root, path)

    # Modo compacto
    if compact:
        if original and isinstance(original, str):
            lines = original.splitlines()
            compacted = []
            prev_empty = False
            for line in lines:
                if line.strip() == '':
                    if not prev_empty:
                        compacted.append('')
                        prev_empty = True
                else:
                    compacted.append(line)
                    prev_empty = False
            original = '\n'.join(compacted)
        if modified and isinstance(modified, str):
            lines = modified.splitlines()
            compacted = []
            prev_empty = False
            for line in lines:
                if line.strip() == '':
                    if not prev_empty:
                        compacted.append('')
                        prev_empty = True
                else:
                    compacted.append(line)
                    prev_empty = False
            modified = '\n'.join(compacted)

    # Números de línea
    if line_nums and diff_style != 'unified':
        if original and isinstance(original, str):
            lines = original.splitlines()
            original = '\n'.join(f"{i+1:4d}: {line}" for i, line in enumerate(lines))
        if modified and isinstance(modified, str):
            lines = modified.splitlines()
            modified = '\n'.join(f"{i+1:4d}: {line}" for i, line in enumerate(lines))

    return {
        'path': path,
        'status': status,
        'language': get_language(os.path.splitext(path)[1], path),
        'original': original,
        'modified': modified,
        'unified_diff': unified,
        'local_mtime': local_mtime,
        'head_mtime': head_mtime
    }

# ─── Función principal ───────────────────────────────────────────────────
def main():
    repo_root = get_git_repo_root()
    os.chdir(repo_root)
    print(colored(f"Repositorio: {repo_root}", Colors.CYAN))

    profile_path = repo_root / '.git_diff_simple_profile.json'
    profile = load_profile(profile_path)
    if profile and input(colored("¿Cargar perfil anterior? (s/n) [s]: ", Colors.CYAN)).strip().lower() != 'n':
        config = profile
    else:
        config = interactive_menu()

    all_changes = get_all_changes(repo_root)
    if not all_changes:
        print(colored("No hay cambios respecto a HEAD.", Colors.GREEN))
        # Diagnóstico extra: si git status no devolvió nada pero no dio error, informamos
        return

    # Cargar patrones de ignorados para diagnóstico
    context_patterns = load_contextignore(repo_root)
    print(colored(f"[DIAGNÓSTICO] Patrones .contextignore: {context_patterns}", Colors.CYAN))

    # Filtrar cambios con registro de motivos de descarte
    status_filters = config['status_filters']
    inc_ext = config['inc_ext']
    exc_pattern = config['exc_pattern']
    filtered = []
    ignored_info = []  # (path, motivo)
    for ch in all_changes:
        path = ch['path']
        # Estado
        if ch['status'] not in status_filters:
            ignored_info.append((path, f"estado {ch['status']} no incluido en filtros {status_filters}"))
            continue
        # Extensión
        ext = os.path.splitext(path)[1].lower()
        if inc_ext and ext not in inc_ext:
            ignored_info.append((path, f"extensión {ext} no incluida en {inc_ext}"))
            continue
        # Patrón de exclusión
        if exc_pattern and fnmatch.fnmatch(path, exc_pattern):
            ignored_info.append((path, f"coincide con patrón de exclusión '{exc_pattern}'"))
            continue
        # .contextignore
        if should_ignore(path, context_patterns):
            ignored_info.append((path, f"ignorado por .contextignore (coincide con algún patrón)"))
            continue
        filtered.append(ch)

    # Mostrar ignorados si hay
    if ignored_info:
        print(colored("\n[DIAGNÓSTICO] Archivos ignorados por filtros:", Colors.WARNING))
        for p, motivo in ignored_info:
            print(f"  - {p}: {motivo}")

    if not filtered:
        print(colored("No hay archivos que cumplan los filtros.", Colors.WARNING))
        if all_changes:
            print(colored("Todos los cambios fueron descartados (ver diagnóstico arriba).", Colors.WARNING))
        return

    print(colored(f"Procesando {len(filtered)} archivos...", Colors.CYAN))

    # Procesamiento paralelo
    files_data = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(process_file, ch, repo_root, config['diff_style'], config['compact'], config['line_numbers']): ch for ch in filtered}
        if HAS_TQDM:
            for future in tqdm(as_completed(futures), total=len(futures), desc="Procesando"):
                files_data.append(future.result())
        else:
            for future in as_completed(futures):
                files_data.append(future.result())

    # Ordenar por fecha si se pidió
    if config.get('sort_by_date', False):
        files_data.sort(key=lambda x: x.get('local_mtime') or 0, reverse=True)

    # Metadatos
    metadata = {
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'system': platform.platform(),
        'user': getpass.getuser(),
        'root': str(repo_root),
        'branch': get_current_branch(),
        'last_commit': get_last_commit()
    }

    # Vista previa
    if config['preview']:
        print(colored("\n=== VISTA PREVIA ===", Colors.BOLD))
        print(f"Archivos a incluir: {len(files_data)}")
        print(f"Estilo diff: {config['diff_style']}")
        print(f"Formato salida: {config['output_format']}")
        if config.get('show_dates', False):
            print("Mostrando fechas de modificación")
        if config.get('sort_by_date', False):
            print("Ordenado por fecha local (más reciente primero)")
        if input(colored("¿Continuar? (s/n) [s]: ", Colors.CYAN)).strip().lower() == 'n':
            return

    # Crear directorio de salida
    output_dir = repo_root / 'git_diff_output'
    output_dir.mkdir(exist_ok=True)

    # Calcular versión
    max_v = 0
    for f in output_dir.glob("git_diff_*.*"):
        try:
            num = int(f.stem.split('_')[-1])
            max_v = max(max_v, num)
        except:
            pass
    version = max_v + 1

    out_files = []
    output_format = config['output_format']
    show_dates = config.get('show_dates', False)
    diff_style = config['diff_style']

    if output_format == 'all':
        for fmt in ['md', 'json', 'xml', 'txt', 'html', 'patch']:
            out_file = output_dir / f'git_diff_{version:03d}.{fmt}'
            if fmt == 'patch':
                content = generate_patch(files_data, metadata, diff_style, show_dates)
            elif fmt == 'json':
                content = generate_json(files_data, metadata, diff_style, show_dates)
            elif fmt == 'xml':
                content = generate_xml(files_data, metadata, diff_style, show_dates)
            elif fmt == 'md':
                content = generate_markdown(files_data, metadata, diff_style, show_dates)
            else:
                func = globals()[f'generate_{fmt}']
                content = func(files_data, metadata, diff_style, show_dates)
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write(content)
            out_files.append(str(out_file))
    elif output_format == 'stats':
        stats = generate_stats(files_data, metadata, diff_style, show_dates)
        print(colored("\n=== ESTADÍSTICAS ===", Colors.BOLD))
        print(stats)
        return
    else:
        out_file = output_dir / f'git_diff_{version:03d}.{output_format}'
        if output_format == 'patch':
            content = generate_patch(files_data, metadata, diff_style, show_dates)
        elif output_format == 'json':
            content = generate_json(files_data, metadata, diff_style, show_dates)
        elif output_format == 'xml':
            content = generate_xml(files_data, metadata, diff_style, show_dates)
        elif output_format == 'md':
            content = generate_markdown(files_data, metadata, diff_style, show_dates)
        else:
            func = globals()[f'generate_{output_format}']
            content = func(files_data, metadata, diff_style, show_dates)
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write(content)
        out_files.append(str(out_file))

    # Mostrar estadísticas en consola
    stats = generate_stats(files_data, metadata, diff_style, show_dates)
    print(colored("\n=== ESTADÍSTICAS ===", Colors.BOLD))
    print(stats)
    print(colored(f"Archivos generados: {', '.join(out_files)}", Colors.GREEN))

    # Copiar al portapapeles si se pidió
    if config['clipboard'] and HAS_CLIPBOARD and out_files:
        try:
            with open(out_files[0], 'r', encoding='utf-8') as f:
                pyperclip.copy(f.read())
            print(colored("Contenido copiado al portapapeles.", Colors.GREEN))
        except Exception as e:
            print(colored(f"No se pudo copiar: {e}", Colors.WARNING))

if __name__ == '__main__':
    main()