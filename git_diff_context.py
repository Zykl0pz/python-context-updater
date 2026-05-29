#!/usr/bin/env python3
"""
Generador de diferencias Git simplificado.
Siempre compara HEAD vs Working Directory, desde la raíz del repo.
Incluye fechas de modificación y ordenamiento por fecha.
"""

import os
import sys
import subprocess
import json
import xml.etree.ElementTree as ET
import platform
import getpass
import fnmatch
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional

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

# ─── Colores ───────────────────────────────────────────────────────────────
class Colors:
    HEADER = '\033[95m'; BLUE = '\033[94m'; CYAN = '\033[96m'
    GREEN = '\033[92m'; WARNING = '\033[93m'; FAIL = '\033[91m'
    ENDC = '\033[0m'; BOLD = '\033[1m'

def colored(text: str, color: str) -> str:
    return f"{color}{text}{Colors.ENDC}" if sys.stdout.isatty() else text

# ─── Utilidades ────────────────────────────────────────────────────────────
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

# ─── Fechas de modificación ───────────────────────────────────────────────
def get_local_mtime(filepath: Path) -> Optional[float]:
    """Devuelve timestamp de modificación local (segundos desde época) o None si no existe."""
    if filepath.exists():
        try:
            return os.path.getmtime(filepath)
        except:
            pass
    return None

def get_head_mtime(repo_root: Path, filepath: str) -> Optional[float]:
    """Devuelve timestamp del último commit que modificó el archivo en HEAD, o None si no existe."""
    try:
        # Obtener la fecha del commit (epoch seconds) del último cambio del archivo en HEAD
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

# ─── Obtener cambios (siempre HEAD vs WD) ─────────────────────────────────
def get_all_changes(repo_root: Path) -> List[Dict]:
    """Retorna lista de cambios desde la raíz del repo."""
    try:
        output = subprocess.check_output(
            ['git', 'status', '--porcelain'],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL
        )
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

def get_original_content(repo_root: Path, path: str) -> Optional[str]:
    try:
        return subprocess.check_output(
            ['git', 'show', f'HEAD:{path}'],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL
        )
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

# ─── Filtros .contextignore (opcional) ────────────────────────────────────
def load_contextignore(repo_root: Path) -> List[str]:
    ignore_file = repo_root / '.contextignore'
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

# ─── Menú interactivo (con opciones de fecha y orden) ──────────────────────
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
    # Filtros por estado
    print(colored("\nFiltrar por tipo de cambio (M,A,D,U,R,C o all):", Colors.HEADER))
    status_choice = input(colored("Selección [all]: ", Colors.CYAN)).strip().lower() or 'all'
    if status_choice == 'all':
        status_filters = ['M','A','D','U','R','C']
    else:
        status_filters = [s.upper() for s in status_choice.split(',') if s.upper() in 'MADURC']
    # Extensiones
    inc_ext = input(colored("Extensiones a incluir (ej. .py,.md) [vacío = todas]: ", Colors.CYAN)).strip()
    inc_ext_list = [e.lower() for e in inc_ext.split(',')] if inc_ext else []
    # Patrón exclusión
    exc_pattern = input(colored("Patrón de exclusión (ej. test_*): ", Colors.CYAN)).strip() or None
    # Estilo diff
    print(colored("\nEstilo de presentación:", Colors.HEADER))
    print("1. Archivo completo (original vs modificado)")
    print("2. Diff unificado (solo líneas cambiadas)")
    print("3. Ambos")
    style = input(colored("Elige (1-3) [1]: ", Colors.CYAN)).strip() or '1'
    diff_style = {'1':'full','2':'unified','3':'both'}[style]
    # Formato salida
    print(colored("\nFormato de salida:", Colors.HEADER))
    print("1. Markdown  2. JSON  3. XML  4. Texto  5. HTML  6. Patch  7. Todos  8. Solo estadísticas")
    fmt = input(colored("Elige (1-8) [1]: ", Colors.CYAN)).strip() or '1'
    fmt_map = {'1':'md','2':'json','3':'xml','4':'txt','5':'html','6':'patch','7':'all','8':'stats'}
    output_format = fmt_map[fmt]
    # Opciones presentación
    compact = input(colored("Modo compacto (reducir líneas vacías)? (s/n) [n]: ", Colors.CYAN)).strip().lower() == 's'
    line_nums = False
    if output_format in ('md', 'all'):
        line_nums = input(colored("Incluir números de línea? (s/n) [n]: ", Colors.CYAN)).strip().lower() == 's'
    # NUEVAS PREGUNTAS: fechas y orden
    show_dates = input(colored("¿Mostrar fechas de modificación (local y en HEAD)? (s/n) [s]: ", Colors.CYAN)).strip().lower() != 'n'
    sort_by_date = False
    if show_dates:
        sort_by_date = input(colored("¿Ordenar archivos por fecha de modificación local (más reciente primero)? (s/n) [n]: ", Colors.CYAN)).strip().lower() == 's'
    preview = input(colored("Vista previa antes de exportar? (s/n) [s]: ", Colors.CYAN)).strip().lower() != 'n'
    clipboard = input(colored("Copiar al portapapeles? (requiere pyperclip) (s/n) [n]: ", Colors.CYAN)).strip().lower() == 's'
    # Guardar perfil
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

# ─── Generación de salidas (incluyendo fechas) ────────────────────────────
def escape_html(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def generate_markdown(files_data: List[Dict], metadata: Dict, diff_style: str, show_dates: bool) -> str:
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
            lines.append(d['original'] if d['original'] else "[No existe en HEAD]\n")
            lines.append("\n```\n#### Modificado\n```\n")
            lines.append(d['modified'] if d['modified'] else "[No existe en WD]\n")
            lines.append("\n```\n")
        if diff_style in ('unified','both') and d.get('unified_diff'):
            lines.append("#### Diff unificado\n```diff\n")
            lines.append(d['unified_diff'])
            lines.append("\n```\n")
        lines.append("---\n\n")
    return ''.join(lines)

def generate_json(files_data: List[Dict], metadata: Dict, _=None, __=None) -> str:
    # Incluye fechas automáticamente porque files_data las contiene
    return json.dumps({'metadata': metadata, 'files': files_data}, indent=2, ensure_ascii=False)

def generate_xml(files_data: List[Dict], metadata: Dict, _=None, __=None) -> str:
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

def generate_txt(files_data: List[Dict], metadata: Dict, diff_style: str, show_dates: bool) -> str:
    lines = [f"GIT DIFF\nGenerado: {metadata['generated']}\nRepositorio: {metadata['root']}\nRama: {metadata['branch']}\n"]
    for d in files_data:
        lines.append(f"\n{'='*60}\nARCHIVO: {d['path']} ({d['language']})\n")
        if show_dates:
            local = format_timestamp(d.get('local_mtime'))
            head = format_timestamp(d.get('head_mtime'))
            lines.append(f"Fecha modificación local: {local}\nFecha en HEAD: {head}\n")
        if diff_style in ('full','both'):
            lines.append("ORIGINAL:\n")
            lines.append(d['original'] if d['original'] else "[No existe]")
            lines.append("\nMODIFICADO:\n")
            lines.append(d['modified'] if d['modified'] else "[No existe]")
        if diff_style in ('unified','both') and d.get('unified_diff'):
            lines.append("\nDIFF:\n")
            lines.append(d['unified_diff'])
    return ''.join(lines)

def generate_html(files_data: List[Dict], metadata: Dict, diff_style: str, show_dates: bool) -> str:
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

def generate_patch(files_data: List[Dict], _=None, __=None, __=None) -> str:
    return '\n'.join(d.get('unified_diff', '') for d in files_data if d.get('unified_diff'))

def generate_stats(files_data: List[Dict], metadata: Dict, _=None, __=None) -> str:
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

# ─── Procesamiento de archivos (con fechas) ───────────────────────────────
def process_file(ch: Dict, repo_root: Path, diff_style: str, compact: bool, line_nums: bool) -> Dict:
    path = ch['path']
    file_path = repo_root / path
    status = ch['status']
    original = None
    modified = None
    unified = None
    # Obtener fechas
    local_mtime = get_local_mtime(file_path) if file_path.exists() else None
    head_mtime = get_head_mtime(repo_root, path) if status not in ('U','A') else None
    if status not in ('U','A'):
        original = get_original_content(repo_root, path)
    if status != 'D' and file_path.exists():
        if is_binary(file_path):
            modified = "[Archivo binario - contenido omitido]"
        else:
            modified = get_current_content(file_path)
    if diff_style in ('unified','both') and status in ('M','A','D','R'):
        unified = get_unified_diff(repo_root, path)
    # Compactar si se solicita
    if compact:
        if original:
            original = '\n'.join([l for l in original.splitlines() if l.strip() != ''] or [''])
        if modified and not modified.startswith("[Archivo binario"):
            modified = '\n'.join([l for l in modified.splitlines() if l.strip() != ''] or [''])
    # Números de línea (solo si no es diff unificado)
    if line_nums and original and diff_style != 'unified':
        lines_orig = original.splitlines()
        original = '\n'.join(f"{i+1:4d}: {l}" for i,l in enumerate(lines_orig))
        if modified and not modified.startswith("[Archivo binario"):
            lines_mod = modified.splitlines()
            modified = '\n'.join(f"{i+1:4d}: {l}" for i,l in enumerate(lines_mod))
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

# ─── Función principal ────────────────────────────────────────────────────
def main():
    repo_root = get_git_repo_root()
    os.chdir(repo_root)  # trabajar desde la raíz
    print(colored(f"Repositorio: {repo_root}", Colors.CYAN))

    # Cargar perfil si existe
    profile_path = repo_root / '.git_diff_simple_profile.json'
    profile = load_profile(profile_path)
    if profile and input(colored("¿Cargar perfil anterior? (s/n) [s]: ", Colors.CYAN)).strip().lower() != 'n':
        config = profile
    else:
        config = interactive_menu()

    # Obtener todos los cambios desde la raíz
    all_changes = get_all_changes(repo_root)
    if not all_changes:
        print(colored("No hay cambios respecto a HEAD.", Colors.GREEN))
        return

    # Aplicar filtros
    status_filters = config['status_filters']
    inc_ext = config['inc_ext']
    exc_pattern = config['exc_pattern']
    filtered = []
    for ch in all_changes:
        if ch['status'] not in status_filters:
            continue
        ext = os.path.splitext(ch['path'])[1].lower()
        if inc_ext and ext not in inc_ext:
            continue
        if exc_pattern and fnmatch.fnmatch(ch['path'], exc_pattern):
            continue
        # Aplicar .contextignore
        context_patterns = load_contextignore(repo_root)
        if should_ignore(ch['path'], context_patterns):
            continue
        filtered.append(ch)

    if not filtered:
        print(colored("No hay archivos que cumplan los filtros.", Colors.WARNING))
        return

    print(colored(f"Procesando {len(filtered)} archivos...", Colors.CYAN))

    # Procesar en paralelo
    files_data = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(process_file, ch, repo_root, config['diff_style'], config['compact'], config['line_numbers']): ch for ch in filtered}
        if HAS_TQDM:
            for future in tqdm(as_completed(futures), total=len(futures), desc="Procesando"):
                files_data.append(future.result())
        else:
            for future in as_completed(futures):
                files_data.append(future.result())

    # Ordenar por fecha si se solicitó
    if config.get('sort_by_date', False):
        # Orden descendente (más reciente primero); los que no tienen fecha van al final
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
    if output_format == 'all':
        for fmt in ['md','json','xml','txt','html','patch']:
            out_file = output_dir / f'git_diff_{version:03d}.{fmt}'
            if fmt == 'patch':
                content = generate_patch(files_data, metadata, None, None)
            else:
                # Llamar a la función de generación correspondiente con los argumentos adecuados
                if fmt == 'json':
                    content = generate_json(files_data, metadata, None, None)
                elif fmt == 'xml':
                    content = generate_xml(files_data, metadata, None, None)
                else:
                    # md, txt, html reciben show_dates y diff_style
                    func = globals()[f'generate_{fmt}']
                    content = func(files_data, metadata, config['diff_style'], show_dates)
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write(content)
            out_files.append(str(out_file))
    elif output_format == 'stats':
        stats = generate_stats(files_data, metadata, None, None)
        print(colored("\n=== ESTADÍSTICAS ===", Colors.BOLD))
        print(stats)
        return
    else:
        out_file = output_dir / f'git_diff_{version:03d}.{output_format}'
        if output_format == 'patch':
            content = generate_patch(files_data, metadata, None, None)
        elif output_format == 'json':
            content = generate_json(files_data, metadata, None, None)
        elif output_format == 'xml':
            content = generate_xml(files_data, metadata, None, None)
        else:
            func = globals()[f'generate_{output_format}']
            content = func(files_data, metadata, config['diff_style'], show_dates)
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write(content)
        out_files.append(str(out_file))

    # Mostrar estadísticas en consola
    stats = generate_stats(files_data, metadata, None, None)
    print(colored("\n=== ESTADÍSTICAS ===", Colors.BOLD))
    print(stats)
    print(colored(f"Archivos generados: {', '.join(out_files)}", Colors.GREEN))

    # Copiar al portapapeles si se solicitó
    if config['clipboard'] and HAS_CLIPBOARD and out_files:
        try:
            with open(out_files[0], 'r', encoding='utf-8') as f:
                pyperclip.copy(f.read())
            print(colored("Contenido copiado al portapapeles.", Colors.GREEN))
        except Exception as e:
            print(colored(f"No se pudo copiar: {e}", Colors.WARNING))

if __name__ == '__main__':
    main()