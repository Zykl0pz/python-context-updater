#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clasificador automático de archivos (modo interactivo + CLI).
Agrupa archivos en subcarpetas según extensión / reglas personalizables.
"""

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Optional, Dict, List

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
LOG_FILE = '.classify_log.json'
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

# ─── Funciones de clasificación ────────────────────────────────────────
def load_rules(directory: Path) -> dict:
    """Carga reglas desde .classify_rules.json si existe, o las por defecto."""
    rules_path = directory / RULES_FILE
    if rules_path.is_file():
        try:
            with open(rules_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error leyendo reglas personalizadas: {e}")
    return DEFAULT_RULES

def get_category(filepath: Path, rules: dict) -> str:
    ext = filepath.suffix.lower()
    return rules.get(ext, 'Otros')

def collect_files(directory: Path, recursive: bool,
                  include: Optional[str], exclude: Optional[str]) -> List[Path]:
    """Recolecta archivos según filtros."""
    files = []
    if recursive:
        for root, _, filenames in os.walk(directory):
            for f in filenames:
                fp = Path(root) / f
                if include and not fp.match(include):
                    continue
                if exclude and fp.match(exclude):
                    continue
                files.append(fp)
    else:
        for item in directory.iterdir():
            if item.is_file():
                if include and not item.match(include):
                    continue
                if exclude and item.match(exclude):
                    continue
                files.append(item)
    return files

def classify(directory: Path, recursive: bool,
             include: Optional[str], exclude: Optional[str],
             dry_run: bool, rules: dict) -> List[dict]:
    files = collect_files(directory, recursive, include, exclude)
    if not files:
        return []

    changes = []
    for f in files:
        cat = get_category(f, rules)
        target_dir = directory / cat
        target = target_dir / f.name
        if f.parent == target_dir:
            continue
        if target.exists():
            stem, ext = f.stem, f.suffix
            i = 1
            while target.exists():
                target = target_dir / f"{stem}_{i}{ext}"
                i += 1
        changes.append({'from': str(f), 'to': str(target), 'category': cat})
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(f), str(target))
                logger.info(f"{f.name} → {cat}/")
            except Exception as e:
                logger.error(f"Error moviendo {f}: {e}")
        else:
            logger.info(f"[SIMULACIÓN] {f.name} → {cat}/{target.name}")
    return changes

def save_log(changes: List[dict], log_path: Path):
    if changes:
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump({'timestamp': str(Path(log_path).stat().st_mtime) if log_path.exists() else '',
                       'changes': changes}, f, indent=2, ensure_ascii=False)
        logger.info(f"Log guardado en {log_path}")

def undo(directory: Path, log_path: Path):
    if not log_path.is_file():
        logger.error(colored(f"No se encontró el log {log_path}", Colors.FAIL))
        return
    with open(log_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    changes = data.get('changes', [])
    if not changes:
        logger.info("El log está vacío.")
        return
    logger.info(f"Deshaciendo {len(changes)} movimientos...")
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
        else:
            logger.warning(f"No se encontró {src}, omitiendo.")
    log_path.unlink()
    logger.info("Log eliminado.")

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

def menu_configuracion() -> dict:
    print(colored("\n=== CONFIGURACIÓN DEL CLASIFICADOR ===", Colors.HEADER + Colors.BOLD))
    config = {}

    perfil = load_profile()
    if perfil:
        usar = input(colored("¿Usar la configuración del perfil? (s/n) [s]: ", Colors.CYAN)).strip().lower()
        if usar in ('', 's', 'si'):
            return perfil

    # Directorio
    while True:
        dir_str = input(colored("Directorio a procesar [.]: ", Colors.CYAN)).strip()
        if not dir_str:
            dir_str = '.'
        try:
            directorio = Path(dir_str).resolve()
            if not directorio.is_dir():
                print(colored("El directorio no existe.", Colors.WARNING))
            else:
                config['directory'] = str(directorio)
                break
        except Exception as e:
            print(colored(f"Error: {e}", Colors.FAIL))

    # Recursivo
    resp = input(colored("¿Incluir subcarpetas? (s/n) [n]: ", Colors.CYAN)).strip().lower()
    config['recursive'] = resp in ('s', 'si')

    # Modo simulación
    resp = input(colored("¿Ejecutar en modo simulación (dry-run)? (s/n) [n]: ", Colors.CYAN)).strip().lower()
    config['dry_run'] = resp in ('s', 'si')

    # Filtros
    inc = input(colored("Patrón de inclusión (glob, ej. *.pdf) [todos]: ", Colors.CYAN)).strip()
    config['include'] = inc if inc else None
    exc = input(colored("Patrón de exclusión (glob, ej. *.tmp) [ninguno]: ", Colors.CYAN)).strip()
    config['exclude'] = exc if exc else None

    # Reglas personalizadas
    rules_choice = input(colored("¿Usar reglas personalizadas desde archivo JSON? (s/n) [n]: ", Colors.CYAN)).strip().lower()
    if rules_choice in ('s', 'si'):
        rules_path = input(colored("Ruta al archivo de reglas: ", Colors.CYAN)).strip()
        try:
            with open(rules_path, 'r', encoding='utf-8') as f:
                rules = json.load(f)
            config['rules'] = rules
        except Exception as e:
            print(colored(f"No se pudo cargar: {e}. Se usarán reglas por defecto.", Colors.WARNING))
            config['rules'] = DEFAULT_RULES
    else:
        config['rules'] = DEFAULT_RULES

    # Guardar perfil
    guardar = input(colored("¿Guardar esta configuración como perfil? (s/n) [s]: ", Colors.CYAN)).strip().lower()
    if guardar in ('', 's', 'si'):
        save_profile(config)

    return config

# ─── Main ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Clasificador automático de archivos")
    parser.add_argument('directory', nargs='?', default=None,
                        help="Directorio a procesar (por defecto: actual)")
    parser.add_argument('-r', '--recursive', action='store_true',
                        help="Incluir subcarpetas")
    parser.add_argument('-n', '--dry-run', action='store_true',
                        help="Sólo simular, sin mover archivos")
    parser.add_argument('--include', help="Patrón glob de inclusión (ej. *.pdf)")
    parser.add_argument('--exclude', help="Patrón glob de exclusión (ej. *.tmp)")
    parser.add_argument('--undo', action='store_true',
                        help="Deshacer la última clasificación")
    parser.add_argument('--rules', help="Archivo JSON con reglas personalizadas")
    args = parser.parse_args()

    # Si se pasó --undo, deshacer y salir
    if args.undo:
        # Determinar directorio: si no se dio, asumir actual
        directory = Path(args.directory) if args.directory else Path.cwd()
        undo(directory, directory / LOG_FILE)
        return

    # Si NO hay argumentos de clasificación (solo se ejecutó el script), modo interactivo
    if not any([args.recursive, args.dry_run, args.include, args.exclude, args.rules]) and args.directory is None:
        config = menu_configuracion()
        directory = Path(config['directory'])
        recursive = config.get('recursive', False)
        dry_run = config.get('dry_run', False)
        include = config.get('include')
        exclude = config.get('exclude')
        rules = config.get('rules', DEFAULT_RULES)
    else:
        # Modo CLI: usar argumentos
        directory = Path(args.directory) if args.directory else Path.cwd()
        recursive = args.recursive
        dry_run = args.dry_run
        include = args.include
        exclude = args.exclude
        if args.rules:
            try:
                with open(args.rules, 'r', encoding='utf-8') as f:
                    rules = json.load(f)
            except Exception as e:
                logger.error(f"No se pudo cargar el archivo de reglas: {e}")
                sys.exit(1)
        else:
            rules = load_rules(directory)

    # Ejecutar clasificación
    changes = classify(directory, recursive, include, exclude, dry_run, rules)
    if not dry_run and changes:
        save_log(changes, directory / LOG_FILE)

    print(colored(f"\nArchivos clasificados: {len(changes)}", Colors.BOLD))
    if dry_run:
        print("(modo simulación: no se realizaron cambios)")

if __name__ == '__main__':
    main()