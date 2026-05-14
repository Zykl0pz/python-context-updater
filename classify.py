#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clasificador automático de archivos (v2.0)
─────────────────────────────────────────
Organiza archivos en carpetas por tipo/extensión con reglas flexibles.
Incluye: filtros avanzados, jerarquía de categorías, conflictos configurables,
         modo espejo, sincronización incremental, histórico de logs, barra de
         progreso, papelera/trash, archivos ocultos/enlaces, informes y
         descarga de reglas desde URL.
"""

import argparse
import csv
import json
import logging
import os
import re
import shutil
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Union

# ─── Dependencias opcionales ───────────────────────────────────────────
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# ─── Colores ANSI ──────────────────────────────────────────────────────
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def colored(text: str, color: str) -> str:
    if sys.stdout.isatty():
        return f"{color}{text}{Colors.ENDC}"
    return text

# ─── Logging ───────────────────────────────────────────────────────────
logger = logging.getLogger('classifier')
logging.basicConfig(format='%(message)s', level=logging.INFO)

# ─── Constantes ────────────────────────────────────────────────────────
PROFILE_FILE = '.classify_profile.json'
LOG_BASENAME = '.classify_log'
RULES_FILE = '.classify_rules.json'
DEFAULT_RULES = {
    '.jpg': 'Imagenes', '.jpeg': 'Imagenes', '.png': 'Imagenes',
    '.gif': 'Imagenes', '.bmp': 'Imagenes', '.tiff': 'Imagenes',
    '.webp': 'Imagenes', '.svg': 'Imagenes', '.ico': 'Imagenes',
    '.raw': 'Imagenes', '.cr2': 'Imagenes', '.nef': 'Imagenes',
    '.pdf': 'Documentos', '.doc': 'Documentos', '.docx': 'Documentos',
    '.xls': 'Documentos', '.xlsx': 'Documentos', '.ppt': 'Documentos',
    '.pptx': 'Documentos', '.odt': 'Documentos', '.ods': 'Documentos',
    '.odp': 'Documentos', '.txt': 'Documentos', '.md': 'Documentos',
    '.rtf': 'Documentos', '.csv': 'Documentos', '.log': 'Documentos',
    '.mp3': 'Audio', '.wav': 'Audio', '.flac': 'Audio',
    '.aac': 'Audio', '.ogg': 'Audio', '.wma': 'Audio',
    '.m4a': 'Audio', '.aiff': 'Audio',
    '.mp4': 'Videos', '.mkv': 'Videos', '.avi': 'Videos',
    '.mov': 'Videos', '.wmv': 'Videos', '.flv': 'Videos',
    '.webm': 'Videos', '.m4v': 'Videos',
    '.py': 'Codigo', '.js': 'Codigo', '.html': 'Codigo',
    '.css': 'Codigo', '.c': 'Codigo', '.cpp': 'Codigo',
    '.h': 'Codigo', '.java': 'Codigo', '.php': 'Codigo',
    '.rb': 'Codigo', '.go': 'Codigo', '.rs': 'Codigo',
    '.sh': 'Codigo', '.bat': 'Codigo', '.ps1': 'Codigo',
    '.json': 'Codigo', '.xml': 'Codigo', '.yaml': 'Codigo',
    '.yml': 'Codigo', '.toml': 'Codigo', '.ini': 'Codigo',
    '.cfg': 'Codigo', '.sql': 'Codigo',
    '.zip': 'Comprimidos', '.rar': 'Comprimidos', '.7z': 'Comprimidos',
    '.tar': 'Comprimidos', '.gz': 'Comprimidos', '.bz2': 'Comprimidos',
    '.xz': 'Comprimidos', '.tgz': 'Comprimidos',
    '.exe': 'Ejecutables', '.msi': 'Ejecutables', '.app': 'Ejecutables',
    '.dmg': 'Ejecutables', '.deb': 'Ejecutables', '.rpm': 'Ejecutables',
}

# ─── Utilidades de fecha ───────────────────────────────────────────────
def parse_date_filter(date_str: str) -> Optional[datetime]:
    """Convierte cadenas como '2025-03-15', '7d', '1w', '2m' a datetime."""
    if not date_str:
        return None
    now = datetime.now()
    if re.match(r'^\d{4}-\d{2}-\d{2}', date_str):
        try:
            return datetime.strptime(date_str[:10], '%Y-%m-%d')
        except ValueError:
            pass
    match = re.match(r'^(\d+)\s*(d|w|m|y)$', date_str, re.IGNORECASE)
    if match:
        num, unit = int(match.group(1)), match.group(2).lower()
        if unit == 'd':
            delta = timedelta(days=num)
        elif unit == 'w':
            delta = timedelta(weeks=num)
        elif unit == 'm':
            delta = timedelta(days=num * 30)  # approx
        elif unit == 'y':
            delta = timedelta(days=num * 365)
        return now - delta
    return None

# ─── Reglas ────────────────────────────────────────────────────────────
def load_rules(rules_source: Union[Path, str, dict]) -> dict:
    """
    Carga reglas desde un archivo, URL o diccionario.
    Si se le pasa un dict, lo usa directamente.
    """
    if isinstance(rules_source, dict):
        return rules_source
    if isinstance(rules_source, Path):
        if rules_source.is_file():
            try:
                with open(rules_source, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error leyendo reglas: {e}")
    if isinstance(rules_source, str):
        # Intenta como ruta local
        local = Path(rules_source)
        if local.is_file():
            return load_rules(local)
        # Intenta como URL
        try:
            with urllib.request.urlopen(rules_source) as response:
                return json.load(response)
        except Exception as e:
            logger.warning(f"No se pudo cargar reglas desde URL: {e}")
    return DEFAULT_RULES

def get_category(filepath: Path, rules: dict) -> str:
    """Obtiene la categoría según las reglas. Soporta extensiones y patrones glob."""
    name = filepath.name
    # Primero busca una regla exacta por extensión (clave que empieza por '.')
    ext = filepath.suffix.lower()
    if ext in rules:
        return rules[ext]
    # Luego busca patrones glob (las claves que no son extensiones puras)
    for pattern, category in rules.items():
        if not pattern.startswith('.'):
            from fnmatch import fnmatch
            if fnmatch(name, pattern):
                return category
    return 'Otros'

# ─── Recolección de archivos (filtros avanzados) ──────────────────────
def collect_files(
    directory: Path,
    recursive: bool = False,
    include: Optional[str] = None,
    exclude: Optional[str] = None,
    include_regex: Optional[str] = None,
    exclude_regex: Optional[str] = None,
    min_size: Optional[int] = None,   # bytes
    max_size: Optional[int] = None,
    newer_than: Optional[datetime] = None,
    older_than: Optional[datetime] = None,
    include_hidden: bool = False,
    follow_symlinks: bool = False,
) -> List[Path]:
    """Lista archivos aplicando todos los filtros."""
    files = []
    if recursive:
        iterator = directory.rglob('*') if not follow_symlinks else directory.rglob('*')
    else:
        iterator = directory.iterdir()

    for item in iterator:
        if not item.is_file():
            continue
        if item.is_symlink() and not follow_symlinks:
            continue
        if not include_hidden and item.name.startswith('.'):
            continue
        # Filtros de nombre
        if include and not item.match(include):
            continue
        if exclude and item.match(exclude):
            continue
        if include_regex and not re.search(include_regex, item.name):
            continue
        if exclude_regex and re.search(exclude_regex, item.name):
            continue
        # Tamaño
        try:
            size = item.stat().st_size
        except OSError:
            continue
        if min_size is not None and size < min_size:
            continue
        if max_size is not None and size > max_size:
            continue
        # Fecha
        try:
            mtime = datetime.fromtimestamp(item.stat().st_mtime)
        except OSError:
            continue
        if newer_than and mtime < newer_than:
            continue
        if older_than and mtime > older_than:
            continue
        files.append(item)
    return files

# ─── Planificación de movimientos ──────────────────────────────────────
def plan_moves(
    files: List[Path],
    directory: Path,
    rules: dict,
    preserve_structure: bool = False,
    move_to: Optional[Path] = None,    # si se especifica, se ignora la categoría
    conflict: str = 'rename',          # 'overwrite', 'skip', 'rename', 'ask'
) -> List[dict]:
    """
    Devuelve una lista de dicts con: from, to, category, action, conflict.
    """
    plans = []
    for f in files:
        if move_to:
            target_dir = move_to
            category = ''
        else:
            category = get_category(f, rules)
            # Jerarquía con '/' en categoría
            target_dir = directory / category.replace('/', os.sep)

        # Preservar estructura original relativa al directorio base
        if preserve_structure and not move_to:
            rel = f.relative_to(directory)
            target_dir = target_dir / rel.parent

        target = target_dir / f.name

        # Saltar si ya está en el lugar correcto
        if f.parent == target_dir and target == f:
            continue

        # Manejar conflictos
        if target.exists():
            if conflict == 'overwrite':
                action = 'overwrite'
            elif conflict == 'skip':
                logger.info(f"Saltado (conflicto): {f.name}")
                continue
            elif conflict == 'rename':
                stem, ext = f.stem, f.suffix
                i = 1
                while target.exists():
                    target = target_dir / f"{stem}_{i}{ext}"
                    i += 1
                action = 'rename'
            elif conflict == 'ask':
                resp = input(f"Conflicto: {target} existe. ¿Sobrescribir? (s/n) ").strip().lower()
                if resp in ('s', 'si'):
                    action = 'overwrite'
                else:
                    logger.info("Omitido por usuario.")
                    continue
        else:
            action = 'move'

        plans.append({
            'from': str(f),
            'to': str(target),
            'category': category,
            'action': action,
        })
    return plans

# ─── Ejecución de movimientos ─────────────────────────────────────────
def execute_moves(plans: List[dict], dry_run: bool = False) -> List[dict]:
    """Mueve los archivos según el plan. Devuelve lista de cambios realizados."""
    changes = []
    iterable = tqdm(plans, desc="Moviendo", unit="archivo") if HAS_TQDM and not dry_run else plans
    for p in iterable:
        src = Path(p['from'])
        dst = Path(p['to'])
        try:
            if not dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                if p['action'] == 'overwrite':
                    if dst.exists():
                        dst.unlink()
                shutil.move(str(src), str(dst))
                changes.append({'from': p['from'], 'to': p['to'], 'category': p['category']})
                logger.info(f"{src.name} → {p['category']+'/' if p['category'] else ''}{dst.name}")
            else:
                logger.info(f"[SIMULACIÓN] {src.name} → {p['category']+'/' if p['category'] else ''}{dst.name}")
        except Exception as e:
            logger.error(f"Error moviendo {src}: {e}")
    return changes

# ─── Gestión de logs históricos ────────────────────────────────────────
def list_logs(directory: Path) -> List[Path]:
    """Devuelve los archivos de log en el directorio ordenados por fecha."""
    logs = sorted(directory.glob(f"{LOG_BASENAME}_*.json"), key=os.path.getmtime, reverse=True)
    return logs

def save_log(changes: List[dict], directory: Path):
    if not changes:
        return
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path = directory / f"{LOG_BASENAME}_{timestamp}.json"
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump({'timestamp': timestamp, 'changes': changes}, f, indent=2, ensure_ascii=False)
    logger.info(f"Log guardado en {log_path}")

def undo_specific_log(log_path: Path):
    if not log_path.is_file():
        logger.error(colored(f"No se encontró el log {log_path}", Colors.FAIL))
        return
    with open(log_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    changes = data.get('changes', [])
    logger.info(f"Deshaciendo {len(changes)} movimientos de {log_path.name}...")
    for change in reversed(changes):
        src = Path(change['to'])
        dst = Path(change['from'])
        if src.exists():
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                logger.info(f"Restaurado: {src.name} → {dst.parent}/")
            except Exception as e:
                logger.error(f"Error deshaciendo {src}: {e}")
    log_path.unlink()
    logger.info("Log eliminado.")

# ─── Informes ─────────────────────────────────────────────────────────
def generate_report(changes: List[dict], directory: Path, fmt: str):
    if not changes:
        return
    if fmt == 'csv':
        report_path = directory / f'classify_report_{datetime.now():%Y%m%d_%H%M%S}.csv'
        with open(report_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Origen', 'Destino', 'Categoría'])
            for c in changes:
                writer.writerow([c['from'], c['to'], c.get('category', '')])
        logger.info(f"Informe CSV guardado en {report_path}")
    elif fmt == 'html':
        # Muy básico
        html = "<html><body><table border='1'><tr><th>Origen</th><th>Destino</th><th>Categoría</th></tr>"
        for c in changes:
            html += f"<tr><td>{c['from']}</td><td>{c['to']}</td><td>{c.get('category','')}</td></tr>"
        html += "</table></body></html>"
        report_path = directory / f'classify_report_{datetime.now():%Y%m%d_%H%M%S}.html'
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html)
        logger.info(f"Informe HTML guardado en {report_path}")
    elif fmt == 'json':
        report_path = directory / f'classify_report_{datetime.now():%Y%m%d_%H%M%S}.json'
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(changes, f, indent=2, ensure_ascii=False)
        logger.info(f"Informe JSON guardado en {report_path}")

# ─── Menú interactivo ──────────────────────────────────────────────────
def load_profile() -> Optional[dict]:
    if Path(PROFILE_FILE).is_file():
        resp = input(colored(f"¿Cargar perfil guardado ({PROFILE_FILE})? (s/n) [s]: ", Colors.CYAN)).strip().lower()
        if resp in ('', 's', 'si'):
            try:
                with open(PROFILE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"No se pudo cargar el perfil: {e}")
    return None

def save_profile(config: dict):
    try:
        with open(PROFILE_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(colored(f"Perfil guardado en {PROFILE_FILE}", Colors.GREEN))
    except Exception as e:
        logger.warning(f"No se pudo guardar el perfil: {e}")

def interactive_menu() -> dict:
    config = {}
    print(colored("\n=== CONFIGURACIÓN DEL CLASIFICADOR ===", Colors.HEADER + Colors.BOLD))

    perfil = load_profile()
    if perfil:
        usar = input(colored("¿Usar la configuración del perfil? (s/n) [s]: ", Colors.CYAN)).strip().lower()
        if usar in ('', 's', 'si'):
            return perfil

    # Directorio
    while True:
        d = input(colored("Directorio a procesar [.]: ", Colors.CYAN)).strip() or '.'
        if Path(d).is_dir():
            config['directory'] = d
            break
        print(colored("No existe.", Colors.WARNING))

    # Recursivo
    config['recursive'] = input(colored("¿Incluir subcarpetas? (s/n) [n]: ", Colors.CYAN)).strip().lower() in ('s','si')

    # Ocultos y enlaces
    config['include_hidden'] = input(colored("¿Incluir archivos ocultos? (s/n) [n]: ", Colors.CYAN)).strip().lower() in ('s','si')
    config['follow_symlinks'] = input(colored("¿Seguir enlaces simbólicos? (s/n) [n]: ", Colors.CYAN)).strip().lower() in ('s','si')

    # Filtros de nombre
    config['include'] = input(colored("Patrón de inclusión (glob, Enter=ninguno): ", Colors.CYAN)).strip() or None
    config['exclude'] = input(colored("Patrón de exclusión (glob): ", Colors.CYAN)).strip() or None
    config['include_regex'] = input(colored("Regex de inclusión: ", Colors.CYAN)).strip() or None
    config['exclude_regex'] = input(colored("Regex de exclusión: ", Colors.CYAN)).strip() or None

    # Tamaño
    min_s = input(colored("Tamaño mínimo (ej. 100KB, 1MB, vacío=sin límite): ", Colors.CYAN)).strip()
    if min_s:
        config['min_size'] = parse_size(min_s)
    max_s = input(colored("Tamaño máximo: ", Colors.CYAN)).strip()
    if max_s:
        config['max_size'] = parse_size(max_s)

    # Fechas
    new_d = input(colored("Más reciente que (YYYY-MM-DD o '7d'): ", Colors.CYAN)).strip()
    if new_d:
        config['newer_than'] = new_d
    old_d = input(colored("Más antiguo que: ", Colors.CYAN)).strip()
    if old_d:
        config['older_than'] = old_d

    # Reglas
    print("\nReglas de clasificación:")
    print("1. Usar reglas por defecto (extensión)")
    print("2. Cargar desde archivo local")
    print("3. Descargar desde URL")
    rules_choice = input(colored("Opción [1]: ", Colors.CYAN)).strip() or '1'
    if rules_choice == '2':
        path = input("Ruta del archivo JSON: ").strip()
        config['rules'] = path  # se cargará después
    elif rules_choice == '3':
        url = input("URL del JSON: ").strip()
        config['rules'] = url
    else:
        config['rules'] = 'default'

    # Modo mover a...
    move_to = input(colored("¿Mover a una carpeta específica (papelera)? (ruta o Enter para no): ", Colors.CYAN)).strip()
    config['move_to'] = move_to if move_to else None

    # Preservar estructura
    if config['recursive'] and not move_to:
        config['preserve_structure'] = input(colored("¿Preservar estructura original? (s/n) [n]: ", Colors.CYAN)).strip().lower() in ('s','si')
    else:
        config['preserve_structure'] = False

    # Conflicto
    print("Manejo de conflictos:")
    print("1. Renombrar (índice)")
    print("2. Sobrescribir")
    print("3. Omitir")
    print("4. Preguntar")
    conflict_choice = input(colored("Opción [1]: ", Colors.CYAN)).strip() or '1'
    config['conflict'] = {'1':'rename','2':'overwrite','3':'skip','4':'ask'}[conflict_choice]

    # Simulación
    config['dry_run'] = input(colored("¿Solo simular? (s/n) [n]: ", Colors.CYAN)).strip().lower() in ('s','si')

    # Informe
    print("Generar informe:")
    print("1. No")
    print("2. CSV")
    print("3. HTML")
    print("4. JSON")
    rep_choice = input(colored("Opción [1]: ", Colors.CYAN)).strip() or '1'
    config['report'] = {'1': None, '2': 'csv', '3': 'html', '4': 'json'}[rep_choice]

    # Guardar perfil
    if input(colored("¿Guardar esta configuración como perfil? (s/n) [s]: ", Colors.CYAN)).strip().lower() in ('','s','si'):
        save_profile(config)

    return config

def parse_size(s: str) -> Optional[int]:
    """Convierte '100KB', '1MB', '2GB' a bytes."""
    s = s.upper().replace(' ', '')
    match = re.match(r'(\d+(?:\.\d+)?)\s*(KB|MB|GB|TB|B)', s)
    if match:
        num = float(match.group(1))
        unit = match.group(2)
        mult = {'B':1, 'KB':1024, 'MB':1024**2, 'GB':1024**3, 'TB':1024**4}
        return int(num * mult[unit])
    return None

# ─── Main ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Clasificador automático de archivos (modo interactivo + CLI)"
    )
    parser.add_argument('directory', nargs='?', default=None,
                        help="Directorio a procesar")
    parser.add_argument('-r', '--recursive', action='store_true',
                        help="Incluir subcarpetas")
    parser.add_argument('-n', '--dry-run', action='store_true',
                        help="Sólo simular")
    # Filtros
    parser.add_argument('--include', help="Patrón glob de inclusión")
    parser.add_argument('--exclude', help="Patrón glob de exclusión")
    parser.add_argument('--include-regex', help="Regex de inclusión")
    parser.add_argument('--exclude-regex', help="Regex de exclusión")
    parser.add_argument('--min-size', help="Tamaño mínimo (ej. 10MB)")
    parser.add_argument('--max-size', help="Tamaño máximo")
    parser.add_argument('--newer-than', help="Más reciente que (YYYY-MM-DD o '7d')")
    parser.add_argument('--older-than', help="Más antiguo que")
    parser.add_argument('--include-hidden', action='store_true', help="Incluir archivos ocultos")
    parser.add_argument('--follow-symlinks', action='store_true', help="Seguir enlaces simbólicos")
    # Movimiento
    parser.add_argument('--move-to', help="Mover todos los archivos a esta carpeta (papelera)")
    parser.add_argument('--preserve-structure', action='store_true',
                        help="Preservar estructura de subcarpetas relativa (solo con --recursive)")
    parser.add_argument('--conflict', choices=['rename','overwrite','skip','ask'], default='rename',
                        help="Manejo de conflictos (default: rename)")
    # Reglas
    parser.add_argument('--rules', help="Archivo local o URL con reglas JSON")
    # Deshacer
    parser.add_argument('--undo', nargs='?', const='last', metavar='LOG_ID',
                        help="Deshacer la última clasificación o una específica (nombre del archivo .json)")
    parser.add_argument('--list-logs', action='store_true', help="Listar logs de deshacer disponibles")
    # Informes
    parser.add_argument('--report', choices=['csv','html','json'], help="Generar informe tras clasificar")

    args = parser.parse_args()

    # Modo listar logs
    if args.list_logs:
        directory = Path(args.directory) if args.directory else Path.cwd()
        logs = list_logs(directory)
        if logs:
            print("Logs disponibles:")
            for log in logs:
                print(f"  {log.name}")
        else:
            print("No hay logs.")
        return

    # Modo deshacer
    if args.undo:
        directory = Path(args.directory) if args.directory else Path.cwd()
        if args.undo == 'last':
            logs = list_logs(directory)
            if not logs:
                print("No hay logs para deshacer.")
                return
            log_path = logs[0]  # más reciente
        else:
            log_path = directory / args.undo
        undo_specific_log(log_path)
        return

    # Si no hay argumentos de clasificación y no se especificó directorio, modo interactivo
    if not any([args.recursive, args.dry_run, args.include, args.exclude,
                args.include_regex, args.exclude_regex, args.min_size,
                args.max_size, args.newer_than, args.older_than,
                args.move_to, args.preserve_structure, args.rules,
                args.report]) and args.directory is None:
        config = interactive_menu()
        directory = Path(config['directory']).resolve()
        recursive = config.get('recursive', False)
        include = config.get('include')
        exclude = config.get('exclude')
        include_regex = config.get('include_regex')
        exclude_regex = config.get('exclude_regex')
        min_size = config.get('min_size')
        max_size = config.get('max_size')
        newer_than_str = config.get('newer_than')
        older_than_str = config.get('older_than')
        include_hidden = config.get('include_hidden', False)
        follow_symlinks = config.get('follow_symlinks', False)
        rules_src = config.get('rules', 'default')
        move_to = config.get('move_to')
        preserve_structure = config.get('preserve_structure', False)
        conflict = config.get('conflict', 'rename')
        dry_run = config.get('dry_run', False)
        report_fmt = config.get('report')
    else:
        # Modo CLI
        directory = Path(args.directory).resolve() if args.directory else Path.cwd()
        recursive = args.recursive
        include = args.include
        exclude = args.exclude
        include_regex = args.include_regex
        exclude_regex = args.exclude_regex
        min_size = parse_size(args.min_size) if args.min_size else None
        max_size = parse_size(args.max_size) if args.max_size else None
        newer_than_str = args.newer_than
        older_than_str = args.older_than
        include_hidden = args.include_hidden
        follow_symlinks = args.follow_symlinks
        rules_src = args.rules if args.rules else 'default'
        move_to = args.move_to
        preserve_structure = args.preserve_structure
        conflict = args.conflict
        dry_run = args.dry_run
        report_fmt = args.report

    # Convertir fechas
    newer_than = parse_date_filter(newer_than_str) if newer_than_str else None
    older_than = parse_date_filter(older_than_str) if older_than_str else None

    # Cargar reglas
    if rules_src == 'default':
        rules = load_rules(directory / RULES_FILE) if (directory / RULES_FILE).exists() else DEFAULT_RULES
    elif isinstance(rules_src, dict):
        rules = rules_src
    else:
        rules = load_rules(rules_src)  # puede ser ruta o URL

    # Carpeta destino especial
    move_to_path = Path(move_to).resolve() if move_to else None

    # Recolectar archivos
    files = collect_files(
        directory, recursive,
        include, exclude, include_regex, exclude_regex,
        min_size, max_size, newer_than, older_than,
        include_hidden, follow_symlinks
    )

    if not files:
        logger.info("No se encontraron archivos con los criterios actuales.")
        return

    # Planificar movimientos
    plans = plan_moves(files, directory, rules, preserve_structure, move_to_path, conflict)
    if not plans:
        logger.info("No hay archivos para mover (ya están clasificados o conflictos omitidos).")
        return

    # Ejecutar (o simular)
    changes = execute_moves(plans, dry_run)

    # Guardar log e informe
    if not dry_run and changes:
        save_log(changes, directory)
        if report_fmt:
            generate_report(changes, directory, report_fmt)

    print(colored(f"\nArchivos procesados: {len(changes)}", Colors.BOLD))
    if dry_run:
        print("(modo simulación: no se realizaron cambios)")

if __name__ == '__main__':
    main()