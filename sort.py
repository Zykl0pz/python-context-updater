#!/usr/bin/env python3
"""
Ordena y renombra archivos con índice numérico (extensible, parametrizable).
Uso básico:
    python ordenar.py --sort-by size --order desc
Modo interactivo completo:
    python ordenar.py --wizard
Deshacer último renombrado:
    python ordenar.py --undo
"""

import os
import sys
import argparse
import json
import fnmatch
import logging
import shutil
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from path_manager import get_repo_dir, get_script_dir, get_instance_dir, get_global_profile_path, get_log_path, get_cache_dir

# ─── Dependencias opcionales ───────────────────────────────────────────────
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

# ─── Colores ANSI ─────────────────────────────────────────────────────────
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def colored(text, color):
    if sys.stdout.isatty():
        return f"{color}{text}{Colors.ENDC}"
    return text

# ─── Logging para deshacer ────────────────────────────────────────────────
RENAME_LOG = str(get_instance_dir(__file__) / ".rename_log.json")
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# ─── Utilidades ───────────────────────────────────────────────────────────
def format_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def detect_script_path():
    """Devuelve la ruta absoluta de este script."""
    return Path(__file__).resolve()

# ─── Gestión de archivos de ignorancia ────────────────────────────────────
DEFAULT_IGNORE_PATTERNS = ['*.pyc', '__pycache__/', '.git/', '.svn/', 'node_modules/']

def load_ignore_file(directory, filename):
    """Lee líneas de un archivo de ignorancia (una por línea)."""
    path = os.path.join(directory, filename)
    if not os.path.isfile(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]

def should_ignore(rel_path, patterns, git_spec, is_dir=False):
    """Comprueba si una ruta relativa debe ser ignorada."""
    # Normalizar separadores
    rel = rel_path.replace(os.sep, '/')
    # Patterns simples (fnmatch)
    for pat in patterns:
        if pat.endswith('/'):
            if rel == pat.rstrip('/') or rel.startswith(pat):
                return True
        else:
            if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(os.path.basename(rel), pat):
                return True
    # Gitignore spec
    if git_spec and git_spec.match_file(rel):
        return True
    return False

def load_gitignore_spec(directory):
    """Carga .gitignore como pathspec si está disponible."""
    if not HAS_PATHSPEC:
        return None
    gi_path = os.path.join(directory, '.gitignore')
    if not os.path.isfile(gi_path):
        return None
    try:
        with open(gi_path, 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()
        return pathspec.PathSpec.from_lines('gitwildmatch', lines)
    except Exception:
        return None

def load_all_ignore(directory):
    """Combina .sortignore y .gitignore."""
    patterns = load_ignore_file(directory, '.sortignore') + DEFAULT_IGNORE_PATTERNS
    git_spec = load_gitignore_spec(directory)
    return patterns, git_spec

# ─── Recopilación de archivos ─────────────────────────────────────────────
def collect_files(directory, recursive, max_depth, include_hidden,
                  include_pat, exclude_pat, positional_paths,
                  ignore_patterns, git_spec):
    """
    Devuelve lista de Path absolutos de archivos que cumplen los filtros.
    Si positional_paths no está vacío, se usan esos (deben ser archivos existentes).
    """
    if positional_paths:
        # Filtrar solo archivos existentes
        files = []
        for p in positional_paths:
            path = Path(p).resolve()
            if path.is_file():
                files.append(path)
            else:
                logger.warning(f"Se omite '{p}' (no es un archivo válido).")
        return files

    base = Path(directory).resolve()
    if not base.is_dir():
        raise NotADirectoryError(f"El directorio '{directory}' no existe.")

    files = []
    if recursive:
        for root, dirs, filenames in os.walk(str(base), followlinks=False):
            # Respetar profundidad máxima
            depth = root[len(str(base)):].count(os.sep)
            if max_depth is not None and depth >= max_depth:
                del dirs[:]  # no descender más
                continue
            # Filtrar directorios ignorados
            rel_root = os.path.relpath(root, str(base))
            if rel_root == '.':
                rel_root = ''
            dirs[:] = [d for d in dirs
                       if not should_ignore(os.path.join(rel_root, d) + '/', ignore_patterns, git_spec, True)]
            for f in filenames:
                rel = os.path.join(rel_root, f) if rel_root else f
                if not should_ignore(rel, ignore_patterns, git_spec):
                    files.append(Path(root) / f)
    else:
        for entry in base.iterdir():
            if entry.is_file():
                rel = entry.relative_to(base)
                if not should_ignore(str(rel), ignore_patterns, git_spec):
                    files.append(entry)

    # Filtrar ocultos
    if not include_hidden:
        files = [f for f in files if not f.name.startswith('.')]

    # Excluir el script mismo
    script = detect_script_path()
    files = [f for f in files if f.resolve() != script]

    # Aplicar include / exclude sobre el nombre del archivo
    if include_pat:
        files = [f for f in files if fnmatch.fnmatch(f.name, include_pat)]
    if exclude_pat:
        files = [f for f in files if not fnmatch.fnmatch(f.name, exclude_pat)]

    return files

# ─── Ordenamiento ─────────────────────────────────────────────────────────
CRITERION_MAP = {
    'mtime': ('mtime', lambda f: f.stat().st_mtime),
    'ctime': ('ctime', lambda f: f.stat().st_ctime),
    'name':  ('name', lambda f: f.name.lower()),
    'namelength': ('namelength', lambda f: len(f.name)),
    'size':  ('size', lambda f: f.stat().st_size),
}

def build_sort_key(primary, tie_breakers, reverse):
    """Construye una función clave que devuelve una tupla."""
    keys = []
    all_criteria = [primary] + (tie_breakers or [])
    for crit in all_criteria:
        if crit not in CRITERION_MAP:
            raise ValueError(f"Criterio desconocido: {crit}")
        keys.append(CRITERION_MAP[crit][1])
    def key_func(f):
        return tuple(k(f) for k in keys)
    return key_func, reverse

# ─── Renombrado ───────────────────────────────────────────────────────────
def validate_filename_length(directory, new_name, max_len=255):
    """Advierte si el nombre supera la longitud típica del sistema."""
    full = os.path.join(directory, new_name)
    if len(full) > max_len:
        logger.warning(colored(f"Nombre largo ({len(full)} caracteres): {full}", Colors.WARNING))

def build_new_name(original, index, format_opts):
    """Construye el nuevo nombre según las opciones de formato."""
    stem = original.stem
    ext = original.suffix
    idx_str = f"{index:0{format_opts['digits']}d}"
    sep = format_opts['sep']
    prefix = format_opts['prefix']
    if format_opts['index_after']:
        # Nombre + sep + índice + extensión
        new_stem = f"{stem}{sep}{idx_str}"
    else:
        # Prefijo + índice + sep + nombre
        new_stem = f"{prefix}{idx_str}{sep}{stem}"
    return new_stem + ext

def perform_rename(files_sorted, format_opts, start_index, dry_run, log_file):
    """Ejecuta el renombrado y guarda el log. Devuelve lista de cambios realizados."""
    changes = []
    conflicts = []
    index = start_index
    for f in files_sorted:
        new_name = build_new_name(f, index, format_opts)
        new_path = f.with_name(new_name)
        index += 1
        if new_path.exists() and new_path != f:
            conflicts.append((f, new_path))
        changes.append((f, new_path))

    if conflicts:
        print(colored("Conflictos detectados (los siguientes destinos ya existen):", Colors.WARNING))
        for orig, dest in conflicts:
            print(f"  {orig.name} -> {dest.name}")
        resp = input("¿Sobrescribir? (s/n): ").strip().lower()
        if resp not in ('s', 'si', 'sí'):
            print("Operación cancelada.")
            return []

    if dry_run:
        print(colored("\nSimulación:", Colors.CYAN))
        for orig, dest in changes:
            status = "CONFLICTO" if dest.exists() and dest != orig else "OK"
            print(f"  {orig.name} -> {dest.name} [{status}]")
        return []

    # Ejecutar
    executed = []
    for orig, dest in changes:
        try:
            orig.replace(dest)  # replace sobreescribe
            print(f"Renombrado: {orig.name} -> {dest.name}")
            executed.append((str(orig), str(dest)))
        except Exception as e:
            logger.error(f"Error renombrando {orig}: {e}")

    # Guardar log
    if log_file:
        log_rename(log_file, executed)
    return executed

def log_rename(log_path, changes):
    """Guarda el mapeo de renombrados en un archivo JSON."""
    if not changes:
        return
    # Asegurar rutas relativas al directorio de ejecución
    data = {
        'timestamp': datetime.now().isoformat(),
        'renames': [{'from': a, 'to': b} for a, b in changes]
    }
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(colored(f"Log guardado en {log_path}", Colors.GREEN))

def undo_rename(log_path=RENAME_LOG):
    """Deshace el último renombrado usando el log."""
    if not os.path.isfile(log_path):
        print(colored(f"No se encontró el log '{log_path}'", Colors.FAIL))
        return
    with open(log_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    renames = data.get('renames', [])
    if not renames:
        print("El log está vacío.")
        return
    print(f"Deshaciendo {len(renames)} renombrados...")
    for entry in renames:
        src = entry['to']  # ahora es el archivo que existe
        dst = entry['from']
        try:
            Path(src).replace(Path(dst))
            print(f"Restaurado: {Path(src).name} -> {Path(dst).name}")
        except Exception as e:
            logger.error(f"Error deshaciendo {src}: {e}")
    # Opcionalmente borrar el log
    os.remove(log_path)
    print("Log eliminado.")

# ─── Asistente interactivo (wizard) ───────────────────────────────────────
def wizard_mode():
    """Modo interactivo completo para configurar todas las opciones."""
    print(colored("\n=== Asistente de ordenamiento ===", Colors.HEADER))
    # Directorio
    directory = input(f"Directorio [{os.getcwd()}]: ").strip() or os.getcwd()
    # Recursivo
    recursive = input("¿Incluir subcarpetas? (s/n) [n]: ").strip().lower() in ('s', 'si')
    max_depth = None
    if recursive:
        depth = input("Profundidad máxima (Enter para ilimitada): ").strip()
        if depth:
            max_depth = int(depth)
    # Ocultos
    hidden = input("¿Incluir archivos ocultos (los que empiezan con '.')? (s/n) [n]: ").strip().lower() in ('s', 'si')
    # Incluir/excluir
    inc = input("Patrón de inclusión (ej. *.txt) [todos]: ").strip() or None
    exc = input("Patrón de exclusión (ej. temp_*) [ninguno]: ").strip() or None
    # Criterio
    print("\nCriterio principal:")
    for key, (name, _) in CRITERION_MAP.items():
        print(f"  {key}: {name}")
    sort_by = input("Opción [name]: ").strip() or 'name'
    if sort_by not in CRITERION_MAP:
        sort_by = 'name'
    # Orden
    order = input("Orden (asc/desc) [asc]: ").strip().lower() or 'asc'
    # Desempate
    tie = input("Criterio de desempate (separado por comas, ej. size,name) [ninguno]: ").strip()
    tie_breakers = [t.strip() for t in tie.split(',') if t.strip() in CRITERION_MAP] if tie else None
    # Formato
    prefix = input("Prefijo [vacío]: ") or ''
    digits = input("Dígitos [3]: ").strip() or '3'
    digits = int(digits)
    sep = input("Separador [_]: ") or '_'
    index_after = input("¿Índice después del nombre? (s/n) [n]: ").strip().lower() in ('s', 'si')
    start_idx = input("Índice inicial [0]: ").strip() or '0'
    start_idx = int(start_idx)
    # Simulación
    dry = input("¿Solo simular (dry-run)? (s/n) [n]: ").strip().lower() in ('s', 'si')

    # Ejecutar
    execute(directory, recursive, max_depth, hidden, inc, exc,
            sort_by, order, tie_breakers,
            prefix, sep, digits, index_after, start_idx, dry, save_log=True)

# ─── Lógica principal ─────────────────────────────────────────────────────
def execute(directory, recursive, max_depth, include_hidden,
            include_pat, exclude_pat, sort_by, order, tie_breakers,
            prefix, sep, digits, index_after, start_index,
            dry_run, save_log=True):
    """Ejecuta la recolección, ordenamiento y renombrado con los parámetros dados."""
    # Cargar ignorancias
    ignore_pat, git_spec = load_all_ignore(directory)

    # Recolectar archivos
    print(colored("Buscando archivos...", Colors.CYAN))
    files = collect_files(directory, recursive, max_depth, include_hidden,
                          include_pat, exclude_pat, [],
                          ignore_pat, git_spec)

    if not files:
        print("No se encontraron archivos que procesar.")
        return

    print(f"Se encontraron {len(files)} archivos.")

    # Ordenar
    reverse = (order == 'desc')
    key_func, rev = build_sort_key(sort_by, tie_breakers, reverse)
    files_sorted = sorted(files, key=key_func, reverse=rev)

    # Mostrar previa (si no es simulación total, mostramos siempre)
    print(colored("\nOrden resultante:", Colors.BOLD))
    for i, f in enumerate(files_sorted, start=start_index):
        new_name = build_new_name(f, i, {'prefix': prefix, 'sep': sep, 'digits': digits, 'index_after': index_after})
        print(f"  {i:0{digits}d}: {f.name} -> {new_name}")

    # Confirmación si no es simulación
    if not dry_run:
        resp = input("\n¿Proceder al renombrado? (s/n): ").strip().lower()
        if resp not in ('s', 'si', 'sí'):
            print("Cancelado.")
            return

    # Renombrar
    log_file = RENAME_LOG if save_log and not dry_run else None
    changes = perform_rename(files_sorted,
                             {'prefix': prefix, 'sep': sep, 'digits': digits, 'index_after': index_after},
                             start_index, dry_run, log_file)

    # Estadísticas
    if changes:
        print(colored(f"\nRenombrados: {len(changes)} archivos.", Colors.GREEN))
    elif dry_run:
        print(colored("Simulación finalizada.", Colors.CYAN))

# ─── Argumentos CLI ───────────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        description="Ordena archivos y los renombra con índice numérico.",
        epilog="Ejemplo: python ordenar.py -s size -o desc --dry-run"
    )
    # Acciones especiales
    parser.add_argument('--undo', action='store_true', help='Deshacer el último renombrado usando el log.')
    parser.add_argument('--wizard', action='store_true', help='Iniciar asistente interactivo completo.')
    # Directorio y archivos
    parser.add_argument('files', nargs='*', help='Archivos específicos a procesar (ignora el directorio).')
    parser.add_argument('-p', '--path', default=os.getcwd(), help='Directorio a procesar (por defecto: actual).')
    # Filtros
    parser.add_argument('-r', '--recursive', action='store_true', help='Incluir subcarpetas.')
    parser.add_argument('--max-depth', type=int, help='Profundidad máxima en modo recursivo.')
    parser.add_argument('--include-hidden', action='store_true', help='Incluir archivos ocultos (los que empiezan con .)')
    parser.add_argument('--include', help='Patrón glob de inclusión (ej. *.jpg)')
    parser.add_argument('--exclude', help='Patrón glob de exclusión (ej. temp_*)')
    # Ordenamiento
    parser.add_argument('-s', '--sort-by', choices=list(CRITERION_MAP.keys()), help='Criterio principal')
    parser.add_argument('-o', '--order', choices=['asc', 'desc'], default='asc', help='Dirección del orden')
    parser.add_argument('-t', '--tie-breaker', nargs='+', choices=list(CRITERION_MAP.keys()),
                        help='Criterios de desempate (si el primero coincide)')
    # Formato
    parser.add_argument('--prefix', default='', help='Prefijo para el índice (antes del número si index-after=False)')
    parser.add_argument('--sep', default='_', help='Separador entre índice y nombre')
    parser.add_argument('--digits', type=int, default=3, help='Cantidad de dígitos (por defecto 3)')
    parser.add_argument('--index-after', action='store_true', help='Poner el índice después del nombre original')
    parser.add_argument('--start', type=int, default=0, help='Índice inicial (por defecto 0)')
    # Ejecución
    parser.add_argument('-n', '--dry-run', action='store_true', help='Solo simular (no renombrar)')
    parser.add_argument('--no-log', action='store_true', help='No guardar .rename_log.json (no se podrá deshacer)')
    parser.add_argument('--profile', help='Cargar un perfil guardado (.sort_profile.json)')
    parser.add_argument('--save-profile', action='store_true', help='Guardar las opciones actuales como perfil')

    return parser.parse_args()

# ─── Gestión de perfiles ─────────────────────────────────────────────────
def save_profile(args, filename=str(get_global_profile_path(__file__, ".sort_profile.json"))):
    """Guarda las opciones relevantes en un JSON."""
    profile = {
        'path': args.path,
        'recursive': args.recursive,
        'max_depth': args.max_depth,
        'include_hidden': args.include_hidden,
        'include': args.include,
        'exclude': args.exclude,
        'sort_by': args.sort_by,
        'order': args.order,
        'tie_breaker': args.tie_breaker,
        'prefix': args.prefix,
        'sep': args.sep,
        'digits': args.digits,
        'index_after': args.index_after,
        'start': args.start,
        'dry_run': args.dry_run,
        'no_log': args.no_log,
    }
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(profile, f, indent=2)
    print(colored(f"Perfil guardado en {filename}", Colors.GREEN))

def load_profile(filename):
    if not os.path.isfile(filename):
        print(colored(f"No se encontró el perfil '{filename}'", Colors.FAIL))
        return None
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

# ─── Punto de entrada ─────────────────────────────────────────────────────
def main():
    args = parse_args()

    # Deshacer
    if args.undo:
        undo_rename()
        return

    # Wizard interactivo completo
    if args.wizard:
        wizard_mode()
        return

    # Si no se pidió wizard ni undo, requerimos al menos criterio y orden para modo no interactivo
    if not args.sort_by and not args.order:
        # Si no hay ningún argumento de orden, podemos caer en una versión simple interactiva
        # o mostrar ayuda. Para mantener compatibilidad, lanzamos el wizard.
        print("No se especificó criterio de orden. Puede usar --wizard o indicar --sort-by y --order.")
        print("Lanzando asistente interactivo...")
        wizard_mode()
        return

    # Cargar perfil si se solicitó
    if args.profile:
        profile = load_profile(args.profile)
        if profile:
            # Actualizar los argumentos con los valores del perfil (los CLI tienen prioridad)
            for key, value in profile.items():
                if getattr(args, key) is None or getattr(args, key) == parser.get_default(key):
                    setattr(args, key, value)

    # Guardar perfil tras cargar/mezclar
    if args.save_profile:
        save_profile(args)

    # Ejecutar
        execute(
            directory=args.path,
            recursive=args.recursive,
            max_depth=args.max_depth,
            include_hidden=args.include_hidden,
            include_pat=args.include,
            exclude_pat=args.exclude,
            sort_by=args.sort_by,
            order=args.order,
            tie_breakers=args.tie_breaker,
            prefix=args.prefix,
            sep=args.sep,
            digits=args.digits,
            index_after=args.index_after,
            start_index=args.start,
            dry_run=args.dry_run,
            save_log=not args.no_log
        )

if __name__ == '__main__':
    main()