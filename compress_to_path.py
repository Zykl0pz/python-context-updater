#!/usr/bin/env python3
"""
Compresor/descompresor interactivo con gestión de archivos ya comprimidos.

Nuevo:
- Si existen archivos comprimidos en el formato seleccionado: se mueven a la carpeta de salida.
- Si están en otro formato soportado (zip, tar.gz, 7z): se transforman al formato destino.
- Para conversión se extrae el contenido y se comprime adecuadamente.
"""

import os
import sys
import zipfile
import tarfile
import json
import shutil
import fnmatch
import time
import logging
import platform
import tempfile
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from path_manager import get_repo_dir, get_script_dir, get_instance_dir, get_global_profile_path, get_log_path, get_cache_dir

# ─── Dependencias opcionales ───────────────────────────────────────────────
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

try:
    import py7zr
    HAS_PY7ZR = True
except ImportError:
    HAS_PY7ZR = False

try:
    import pyzipper
    HAS_PYZIPPER = True
except ImportError:
    HAS_PYZIPPER = False

try:
    from send2trash import send2trash
    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False

# ─── Colores ANSI ──────────────────────────────────────────────────────────
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def colored(text, color):
    if sys.stdout.isatty():
        return f"{color}{text}{Colors.ENDC}"
    return text

# ─── Logging ──────────────────────────────────────────────────────────────
logger = logging.getLogger('compresor')
logger.setLevel(logging.DEBUG)

def setup_logging(quiet: bool, log_file: Optional[str] = None):
    logger.handlers.clear()
    if log_file:
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(fh)
    if not quiet:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter('%(message)s'))
    else:
        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(logging.WARNING)
        ch.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(ch)

# ─── Utilidades ────────────────────────────────────────────────────────────
def format_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def format_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f} s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins} min {secs:.0f} s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours} h {mins} min"

def prompt_yes_no(question: str, default: str = "n") -> bool:
    choices = " (s/n)" if default == "n" else " (S/n)"
    resp = input(colored(question + choices + ": ", Colors.CYAN)).strip().lower()
    if not resp:
        return default.lower() == "s"
    return resp in ('s', 'si', 'y', 'yes')

def prompt_int(question: str, default: int, min_val: int = None, max_val: int = None) -> int:
    while True:
        resp = input(colored(f"{question} [{default}]: ", Colors.CYAN)).strip()
        if not resp:
            return default
        try:
            val = int(resp)
            if (min_val is not None and val < min_val) or (max_val is not None and val > max_val):
                print(colored(f"Valor entre {min_val} y {max_val}.", Colors.WARNING))
                continue
            return val
        except ValueError:
            print(colored("Por favor, introduce un número entero.", Colors.WARNING))

def prompt_path(question: str, default: str = ".") -> Path:
    resp = input(colored(f"{question} [{default}]: ", Colors.CYAN)).strip()
    path = Path(resp) if resp else Path(default)
    return path.resolve()

def prompt_date(question: str) -> Optional[datetime]:
    while True:
        resp = input(colored(f"{question} (YYYY-MM-DD, Enter = omitir): ", Colors.CYAN)).strip()
        if not resp:
            return None
        try:
            return datetime.strptime(resp, "%Y-%m-%d")
        except ValueError:
            print(colored("Formato inválido. Usa AAAA-MM-DD.", Colors.WARNING))

def prompt_file_patterns():
    inc = input(colored("Patrón de inclusión (ej. test_*.py) [Enter = todos]: ", Colors.CYAN)).strip()
    exc = input(colored("Patrón de exclusión (ej. *.min.*) [Enter = ninguno]: ", Colors.CYAN)).strip()
    return inc or None, exc or None

# ─── Perfil persistente ──────────────────────────────────────────────────
PROFILE_FILE = str(get_global_profile_path(__file__, ".compress_profile.json"))

def load_profile() -> Optional[Dict[str, Any]]:
    if os.path.isfile(PROFILE_FILE):
        if prompt_yes_no("¿Cargar perfil anterior?", "s"):
            try:
                with open(PROFILE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"No se pudo cargar perfil: {e}")
    return None

def save_profile(profile: Dict[str, Any]):
    if prompt_yes_no("¿Guardar este perfil para futuras ejecuciones?", "n"):
        try:
            with open(PROFILE_FILE, 'w', encoding='utf-8') as f:
                json.dump(profile, f, indent=2)
            logger.info(colored("Perfil guardado.", Colors.GREEN))
        except Exception as e:
            logger.warning(f"No se pudo guardar perfil: {e}")

# ─── Metadatos Unix ────────────────────────────────────────────────────────
def get_unix_metadata(filepath: Path) -> Dict[str, Any]:
    if platform.system() == 'Windows':
        return {}
    stat = os.stat(filepath)
    try:
        import pwd, grp
        owner = pwd.getpwuid(stat.st_uid).pw_name
        group = grp.getgrgid(stat.st_gid).gr_name
    except Exception:
        owner = str(stat.st_uid)
        group = str(stat.st_gid)
    return {
        'mode': oct(stat.st_mode)[-3:],
        'owner': owner,
        'group': group,
        'mtime': stat.st_mtime,
        'atime': stat.st_atime
    }

def restore_unix_metadata(filepath: Path, meta: Dict[str, Any]):
    try:
        os.chmod(filepath, int(meta['mode'], 8))
        os.utime(filepath, (meta['atime'], meta['mtime']))
    except Exception as e:
        logger.warning(f"No se pudieron restaurar metadatos de {filepath}: {e}")

# ─── Operaciones de compresión ─────────────────────────────────────────────
def compress_file_zip(file: Path, output: Path, level: int, overwrite: bool,
                      password: Optional[str] = None, split_size: int = 0) -> Tuple[str, bool, int, int, str]:
    if not overwrite and output.exists():
        return (file.name, False, 0, 0, "ya existe (omitido)")
    try:
        original_size = file.stat().st_size
        if not split_size or original_size <= split_size:
            if password and HAS_PYZIPPER:
                with pyzipper.AESZipFile(output, 'w', compression=pyzipper.ZIP_DEFLATED, compresslevel=level,
                                         encryption=pyzipper.WZ_AES) as zf:
                    zf.setpassword(password.encode())
                    zf.write(file, arcname=file.name)
            else:
                if password:
                    logger.warning("pyzipper no instalado, se omite la contraseña.")
                with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=level) as zf:
                    zf.write(file, arcname=file.name)
            compressed_size = output.stat().st_size
            return (file.name, True, original_size, compressed_size, "")
        else:
            base = output.stem
            dest_dir = output.parent
            part_num = 1
            total_compressed = 0
            with open(file, 'rb') as f_in:
                while True:
                    chunk = f_in.read(split_size)
                    if not chunk:
                        break
                    part_name = f"{base}.part{part_num:03d}.zip"
                    part_path = dest_dir / part_name
                    with zipfile.ZipFile(part_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=level) as zf:
                        zf.writestr(f"{file.name}.part{part_num:03d}", chunk)
                    total_compressed += part_path.stat().st_size
                    part_num += 1
            return (file.name, True, original_size, total_compressed, f"en {part_num-1} volúmenes")
    except PermissionError as e:
        return (file.name, False, 0, 0, f"Permiso denegado: {e}")
    except Exception as e:
        return (file.name, False, 0, 0, str(e))

def compress_file_targz(file: Path, output: Path, overwrite: bool) -> Tuple[str, bool, int, int, str]:
    if not overwrite and output.exists():
        return (file.name, False, 0, 0, "ya existe (omitido)")
    try:
        original_size = file.stat().st_size
        with tarfile.open(output, 'w:gz') as tar:
            tar.add(file, arcname=file.name)
        compressed_size = output.stat().st_size
        return (file.name, True, original_size, compressed_size, "")
    except Exception as e:
        return (file.name, False, 0, 0, str(e))

def compress_file_7z(file: Path, output: Path, overwrite: bool, password: Optional[str] = None) -> Tuple[str, bool, int, int, str]:
    if not overwrite and output.exists():
        return (file.name, False, 0, 0, "ya existe (omitido)")
    try:
        original_size = file.stat().st_size
        with py7zr.SevenZipFile(output, 'w', password=password) as archive:
            archive.writeall(file, arcname=file.name)
        compressed_size = output.stat().st_size
        return (file.name, True, original_size, compressed_size, "")
    except Exception as e:
        return (file.name, False, 0, 0, str(e))

def compress_file_subdir(dir_path: Path, output: Path, format_type: str,
                         level: int, overwrite: bool, password: Optional[str] = None) -> Tuple[str, bool, int, int, str]:
    if not overwrite and output.exists():
        return (dir_path.name, False, 0, 0, "ya existe (omitido)")
    try:
        original_size = sum(f.stat().st_size for f in dir_path.rglob('*') if f.is_file())
        if format_type == 'zip':
            if password and HAS_PYZIPPER:
                with pyzipper.AESZipFile(output, 'w', compression=pyzipper.ZIP_DEFLATED, compresslevel=level,
                                         encryption=pyzipper.WZ_AES) as zf:
                    zf.setpassword(password.encode())
                    for f in dir_path.rglob('*'):
                        if f.is_file():
                            zf.write(f, arcname=f.relative_to(dir_path.parent))
            else:
                if password:
                    logger.warning("pyzipper no instalado, se omite contraseña.")
                with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=level) as zf:
                    for f in dir_path.rglob('*'):
                        if f.is_file():
                            zf.write(f, arcname=f.relative_to(dir_path.parent))
        elif format_type == 'tar.gz':
            with tarfile.open(output, 'w:gz') as tar:
                for f in dir_path.rglob('*'):
                    if f.is_file():
                        tar.add(f, arcname=f.relative_to(dir_path.parent))
        elif format_type == '7z':
            with py7zr.SevenZipFile(output, 'w', password=password) as archive:
                archive.writeall(dir_path, arcname=dir_path.name)
        compressed_size = output.stat().st_size
        return (dir_path.name, True, original_size, compressed_size, "")
    except Exception as e:
        return (dir_path.name, False, 0, 0, str(e))

# ─── Escaneo de archivos ────────────────────────────────────────────────────
INCOMPRESSIBLE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif',
    '.mp3', '.mp4', '.avi', '.mkv', '.mov', '.flac', '.aac',
    '.zip', '.7z', '.rar', '.gz', '.bz2', '.xz', '.tgz',
    '.pdf', '.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp'
}

def should_ignore_compressed(ext: str, skip_incompressible: bool) -> bool:
    return ext.lower() in INCOMPRESSIBLE_EXTENSIONS and skip_incompressible

def collect_files(root_dir: Path, recursive: bool, include_hidden: bool,
                  exclude_exts: set, skip_incompressible: bool,
                  include_pat: Optional[str], exclude_pat: Optional[str],
                  min_size: Optional[int], max_size: Optional[int],
                  after_date: Optional[datetime], before_date: Optional[datetime],
                  output_dir: Optional[Path] = None) -> List[Path]:
    files = []
    pattern = "**/*" if recursive else "*"
    for entry in root_dir.glob(pattern):
        if not entry.is_file():
            continue
        if not include_hidden and entry.name.startswith('.'):
            continue
        if entry.suffix.lower() in exclude_exts:
            continue
        if should_ignore_compressed(entry.suffix, skip_incompressible):
            logger.info(f"Omitiendo formato ya comprimido: {entry.name}")
            continue
        if include_pat and not fnmatch.fnmatch(entry.name, include_pat):
            continue
        if exclude_pat and fnmatch.fnmatch(entry.name, exclude_pat):
            continue
        size = entry.stat().st_size
        if min_size is not None and size < min_size:
            continue
        if max_size is not None and size > max_size:
            continue
        mtime = datetime.fromtimestamp(entry.stat().st_mtime)
        if after_date and mtime < after_date:
            continue
        if before_date and mtime > before_date:
            continue
        if output_dir:
            try:
                if output_dir in entry.parents or entry.parent == output_dir:
                    continue
            except ValueError:
                pass
        files.append(entry)
    return files

# ─── Gestión de archivos ya comprimidos ────────────────────────────────────
ARCHIVE_EXTENSIONS = {'.zip', '.tar.gz', '.tgz', '.7z'}

def is_archive_file(filepath: Path) -> Optional[str]:
    """Devuelve el formato ('zip','tar.gz','7z') o None si no es un archivo comprimido conocido."""
    name = filepath.name.lower()
    if name.endswith('.tar.gz') or name.endswith('.tgz'):
        return 'tar.gz'
    elif name.endswith('.zip'):
        return 'zip'
    elif name.endswith('.7z'):
        return '7z'
    return None

def collect_archives(root_dir: Path, recursive: bool, include_hidden: bool) -> List[Path]:
    """Recolecta archivos que son comprimidos conocidos."""
    archives = []
    pattern = "**/*" if recursive else "*"
    for entry in root_dir.glob(pattern):
        if not entry.is_file():
            continue
        if not include_hidden and entry.name.startswith('.'):
            continue
        if is_archive_file(entry):
            archives.append(entry)
    return archives

def extract_archive(archive_path: Path, extract_to: Path) -> bool:
    """Extrae el contenido del archivo comprimido a extract_to. Retorna True si fue exitoso."""
    fmt = is_archive_file(archive_path)
    try:
        if fmt == 'zip':
            with zipfile.ZipFile(archive_path, 'r') as zf:
                # Comprobar si está cifrado
                for info in zf.infolist():
                    if info.flag_bits & 0x1:  # bit de encriptación
                        logger.warning(f"El ZIP {archive_path.name} está cifrado; no se puede convertir automáticamente.")
                        return False
                zf.extractall(extract_to)
        elif fmt == 'tar.gz':
            with tarfile.open(archive_path, 'r:gz') as tar:
                tar.extractall(extract_to)
        elif fmt == '7z':
            if not HAS_PY7ZR:
                logger.warning(f"py7zr no instalado, no se puede extraer {archive_path.name}")
                return False
            with py7zr.SevenZipFile(archive_path, 'r') as z7:
                z7.extractall(extract_to)
        return True
    except Exception as e:
        logger.warning(f"Error extrayendo {archive_path.name}: {e}")
        return False

def compress_extracted_content(source_dir: Path, output_path: Path, target_format: str,
                               level: int, overwrite: bool, password: Optional[str] = None) -> Tuple[bool, int, int]:
    """
    Comprime el contenido de source_dir en output_path.
    Si hay un único archivo (sin subdirectorios), comprime solo ese archivo.
    Devuelve (éxito, tamaño_original, tamaño_comprimido).
    """
    if not overwrite and output_path.exists():
        return (False, 0, 0)

    # Listar contenido inmediato
    entries = list(source_dir.iterdir())
    files_only = [e for e in entries if e.is_file()]
    dirs = [e for e in entries if e.is_dir()]

    # Calcular tamaño original
    total_original = sum(f.stat().st_size for f in source_dir.rglob('*') if f.is_file())

    try:
        # Caso: un único archivo y ninguna carpeta → comprimir ese archivo suelto
        if len(files_only) == 1 and len(dirs) == 0:
            file_to_compress = files_only[0]
            if target_format == 'zip':
                result = compress_file_zip(file_to_compress, output_path, level, overwrite, password, 0)
                return (result[1], result[2], result[3])
            elif target_format == 'tar.gz':
                result = compress_file_targz(file_to_compress, output_path, overwrite)
                return (result[1], result[2], result[3])
            elif target_format == '7z':
                result = compress_file_7z(file_to_compress, output_path, overwrite, password)
                return (result[1], result[2], result[3])
        else:
            # Varios archivos o carpetas → comprimir el directorio completo
            if target_format == 'zip':
                if password and HAS_PYZIPPER:
                    with pyzipper.AESZipFile(output_path, 'w', compression=pyzipper.ZIP_DEFLATED, compresslevel=level,
                                             encryption=pyzipper.WZ_AES) as zf:
                        zf.setpassword(password.encode())
                        for f in source_dir.rglob('*'):
                            if f.is_file():
                                zf.write(f, arcname=f.relative_to(source_dir))
                else:
                    if password:
                        logger.warning("pyzipper no instalado, se omite la contraseña.")
                    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=level) as zf:
                        for f in source_dir.rglob('*'):
                            if f.is_file():
                                zf.write(f, arcname=f.relative_to(source_dir))
            elif target_format == 'tar.gz':
                with tarfile.open(output_path, 'w:gz') as tar:
                    for f in source_dir.rglob('*'):
                        if f.is_file():
                            tar.add(f, arcname=f.relative_to(source_dir))
            elif target_format == '7z':
                with py7zr.SevenZipFile(output_path, 'w', password=password) as archive:
                    archive.writeall(source_dir, arcname=output_path.stem)
            compressed_size = output_path.stat().st_size
            return (True, total_original, compressed_size)
    except Exception as e:
        logger.error(f"Error creando archivo convertido {output_path}: {e}")
        return (False, total_original, 0)

def process_existing_archives(input_dir: Path, output_dir: Path, target_format: str,
                              recursive: bool, include_hidden: bool, overwrite: bool,
                              level: int, password: Optional[str], remove_original: bool) -> Tuple[int, int, int]:
    """
    Procesa archivos comprimidos existentes:
    - Si el formato coincide con target: los mueve al output.
    - Si no, los convierte al formato destino.
    Retorna (archivos_movidos, archivos_convertidos, total_bytes_ahorro).
    """
    archives = collect_archives(input_dir, recursive, include_hidden)
    moved = 0
    converted = 0
    total_original = 0
    total_compressed = 0

    for arch in archives:
        fmt = is_archive_file(arch)
        if fmt is None:
            continue

        # Evitar procesar si ya está dentro de la carpeta de salida
        try:
            if output_dir in arch.parents or arch.parent == output_dir:
                continue
        except ValueError:
            pass

        dest_name = arch.stem  # sin extensión del formato
        if target_format == 'zip':
            dest_ext = '.zip'
        elif target_format == 'tar.gz':
            dest_ext = '.tar.gz'
        elif target_format == '7z':
            dest_ext = '.7z'
        dest_path = output_dir / (dest_name + dest_ext)

        if fmt == target_format:
            # Mover el archivo a la carpeta de salida
            if not overwrite and dest_path.exists():
                logger.info(f"El archivo {dest_path.name} ya existe en destino, omitiendo mover {arch.name}")
                continue
            try:
                shutil.move(str(arch), str(dest_path))
                logger.info(f"Movido: {arch.name} → {dest_path}")
                moved += 1
                # Contabilizamos tamaños para estadísticas (se asume que no cambia)
                total_original += arch.stat().st_size
                total_compressed += arch.stat().st_size
            except Exception as e:
                logger.warning(f"No se pudo mover {arch.name}: {e}")
        else:
            # Convertir a formato destino
            if not overwrite and dest_path.exists():
                logger.info(f"Ya existe {dest_path.name}, omitiendo conversión de {arch.name}")
                continue

            with tempfile.TemporaryDirectory() as tmpdir:
                tmp = Path(tmpdir)
                if extract_archive(arch, tmp):
                    success, orig, comp = compress_extracted_content(tmp, dest_path, target_format,
                                                                     level, overwrite, password)
                    if success:
                        total_original += orig
                        total_compressed += comp
                        converted += 1
                        logger.info(f"Convertido: {arch.name} → {dest_path}")
                        if remove_original:
                            try:
                                arch.unlink()
                                logger.info(f"Eliminado original: {arch.name}")
                            except Exception as e:
                                logger.warning(f"No se pudo eliminar original {arch.name}: {e}")
                    else:
                        logger.warning(f"Falló la conversión de {arch.name}")

    ahorro = total_original - total_compressed
    return (moved, converted, ahorro)

# ─── Restauración ─────────────────────────────────────────────────────────
def restore_archives(source_dir: Path, target_dir: Path, overwrite: bool):
    archives = list(source_dir.glob('*.zip')) + list(source_dir.glob('*.tar.gz')) + \
               (list(source_dir.glob('*.7z')) if HAS_PY7ZR else [])
    if not archives:
        logger.info("No se encontraron archivos comprimidos para restaurar.")
        return
    logger.info(f"Se restaurarán {len(archives)} archivo(s).")
    target_dir.mkdir(exist_ok=True)
    for arch in archives:
        try:
            ext = arch.suffix
            if ext == '.zip':
                with zipfile.ZipFile(arch, 'r') as zf:
                    zf.extractall(target_dir)
            elif ext == '.gz' and arch.name.endswith('.tar.gz'):
                with tarfile.open(arch, 'r:gz') as tar:
                    tar.extractall(target_dir)
            elif ext == '.7z' and HAS_PY7ZR:
                with py7zr.SevenZipFile(arch, 'r') as z7:
                    z7.extractall(target_dir)
            else:
                logger.warning(f"Formato no soportado para restauración: {arch.name}")
            logger.info(f"Restaurado: {arch.name}")
        except Exception as e:
            logger.warning(f"Error restaurando {arch.name}: {e}")

# ─── Función principal ─────────────────────────────────────────────────────
def main():
    print(colored("\n=== COMPRESOR/DESCOMPRESOR INTERACTIVO ===", Colors.BOLD + Colors.HEADER))

    # Elegir operación
    while True:
        opcion = input(colored(
            "¿Qué deseas hacer? 1=Comprimir archivos, 2=Restaurar archivos [1]: ", Colors.CYAN)).strip()
        if not opcion or opcion == '1':
            compression_mode = True
            break
        elif opcion == '2':
            compression_mode = False
            break
        else:
            print(colored("Opción no válida.", Colors.WARNING))

    if not compression_mode:
        src = prompt_path("Directorio donde están los archivos comprimidos", "comprimidos")
        if not src.is_dir():
            print(colored("El directorio no existe.", Colors.FAIL))
            return
        target = prompt_path("Directorio destino para la restauración", "restaurados")
        overwrite = prompt_yes_no("¿Sobrescribir archivos existentes?", "n")
        restore_archives(src, target, overwrite)
        return

    # ─── Modo compresión ──────────────────────────────────────────────────
    profile = load_profile()
    if profile:
        input_dir = Path(profile['input_dir'])
        output_dir = Path(profile['output_dir'])
        exclude_exts = set(profile.get('exclude_exts', []))
        include_hidden = profile.get('include_hidden', False)
        recursive = profile.get('recursive', False)
        overwrite = profile.get('overwrite', False)
        compression_level = profile.get('compression_level', 8)
        parallel = profile.get('parallel', 1)
        quiet = profile.get('quiet', False)
        log_file = profile.get('log_file', None)
        format_type = profile.get('format', 'zip')
        password = profile.get('password', None)
        split_size = profile.get('split_size', 0)
        skip_incompressible = profile.get('skip_incompressible', True)
        min_size = profile.get('min_size')
        max_size = profile.get('max_size')
        after_date_str = profile.get('after_date')
        before_date_str = profile.get('before_date')
        after_date = datetime.fromisoformat(after_date_str) if after_date_str else None
        before_date = datetime.fromisoformat(before_date_str) if before_date_str else None
        include_pat = profile.get('include_pat')
        exclude_pat = profile.get('exclude_pat')
        dry_run = profile.get('dry_run', False)
        move_to_trash = profile.get('move_to_trash', False)
        compress_subdirs = profile.get('compress_subdirs', False)
        preserve_meta = profile.get('preserve_meta', False)
        process_archives = profile.get('process_archives', False)
        remove_original_after_conversion = profile.get('remove_original_after_conversion', False)
        print(colored("Perfil cargado.", Colors.GREEN))
    else:
        input_dir = prompt_path("Directorio de entrada", ".")
        if not input_dir.is_dir():
            print(colored(f"El directorio {input_dir} no existe.", Colors.FAIL))
            return
        output_dir = prompt_path("Carpeta de salida para los archivos comprimidos", "comprimidos")
        try:
            output_dir.mkdir(exist_ok=True)
        except PermissionError:
            print(colored(f"Sin permisos para crear {output_dir}", Colors.FAIL))
            return

        # Selección del formato
        format_choices = ['ZIP (zip)', 'TAR.GZ (tar.gz)']
        if HAS_PY7ZR:
            format_choices.append('7z (7z)')
        else:
            logger.warning("py7zr no instalado, opción 7z no disponible.")
        print(colored("\nFormatos disponibles:", Colors.HEADER))
        for i, f in enumerate(format_choices, 1):
            print(f"  {i}. {f}")
        fmt_sel = input(colored("Elige el formato (número) [1]: ", Colors.CYAN)).strip() or '1'
        if fmt_sel == '1':
            format_type = 'zip'
        elif fmt_sel == '2':
            format_type = 'tar.gz'
        elif fmt_sel == '3' and HAS_PY7ZR:
            format_type = '7z'
        else:
            print(colored("Selección no válida, usando ZIP.", Colors.WARNING))
            format_type = 'zip'

        # Contraseña
        password = None
        if format_type in ('zip', '7z'):
            if prompt_yes_no("¿Proteger con contraseña?", "n"):
                password = input(colored("Contraseña: ", Colors.CYAN)).strip()
                if not password:
                    print(colored("Contraseña vacía, se omite protección.", Colors.WARNING))
                    password = None

        # División en volúmenes (solo ZIP)
        split_size = 0
        if format_type == 'zip':
            if prompt_yes_no("¿Dividir archivos grandes en volúmenes?", "n"):
                split_size_mb = prompt_int("Tamaño máximo de cada volumen (MB)", 100, 1, 100000)
                split_size = split_size_mb * 1024 * 1024

        # Exclusiones de extensiones
        exts_str = input(colored("Extensiones a excluir (sin punto, separadas por espacios) [ninguna]: ", Colors.CYAN)).strip()
        exclude_exts = {f".{e.lstrip('.').lower()}" for e in exts_str.split()} if exts_str else set()
        exclude_exts.add(".zip")  # siempre ignorar ZIPs

        # Otras opciones
        include_hidden = prompt_yes_no("¿Incluir archivos ocultos?", "n")
        recursive = prompt_yes_no("¿Modo recursivo?", "n")
        overwrite = prompt_yes_no("¿Sobrescribir archivos comprimidos existentes?", "n")
        compression_level = prompt_int("Nivel de compresión (0-9, solo ZIP/7z)", 8, 0, 9) if format_type in ('zip', '7z') else 0
        parallel = prompt_int("Número de hilos para compresión en paralelo (1=secuencial)", 1, 1, 32)
        quiet = prompt_yes_no("¿Modo silencioso (solo errores)?", "n")
        log_file = None
        if prompt_yes_no("¿Guardar registro en archivo de log?", "n"):
            log_file = input(colored("Nombre del archivo de log [compresor.log]: ", Colors.CYAN)).strip() or str(get_log_path(__file__, "compresor.log"))

        # Filtros avanzados
        print(colored("\nFiltros avanzados:", Colors.HEADER))
        skip_incompressible = prompt_yes_no("¿Omitir formatos ya comprimidos (jpg, mp3, etc.)?", "s")
        min_size_mb = input(colored("Tamaño mínimo en MB (Enter = sin límite): ", Colors.CYAN)).strip()
        min_size = int(float(min_size_mb) * 1024 * 1024) if min_size_mb else None
        max_size_mb = input(colored("Tamaño máximo en MB (Enter = sin límite): ", Colors.CYAN)).strip()
        max_size = int(float(max_size_mb) * 1024 * 1024) if max_size_mb else None
        after_date = prompt_date("Solo archivos modificados después de")
        before_date = prompt_date("Solo archivos modificados antes de")
        include_pat, exclude_pat = prompt_file_patterns()

        compress_subdirs = prompt_yes_no("¿Comprimir cada subdirectorio como un solo archivo?", "n")
        dry_run = prompt_yes_no("¿Modo simulación (solo mostrar qué se hará)?", "n")
        move_to_trash = False
        if not dry_run:
            if prompt_yes_no("¿Mover originales a la papelera tras comprimir con éxito?", "n"):
                if not HAS_SEND2TRASH:
                    logger.warning("send2trash no instalado, no se podrá mover a papelera.")
                else:
                    move_to_trash = True

        preserve_meta = False
        if platform.system() != 'Windows':
            preserve_meta = prompt_yes_no("¿Preservar metadatos Unix (permisos, propietario) en un JSON?", "n")

        # ─── NUEVA OPCIÓN: Procesar archivos ya comprimidos ────────────────
        process_archives = prompt_yes_no("¿Procesar archivos ya comprimidos? (mover si formato destino, convertir otros)", "n")
        remove_original_after_conversion = False
        if process_archives:
            remove_original_after_conversion = prompt_yes_no(
                "¿Eliminar archivos originales tras conversión exitosa?", "n")

        # Guardar perfil
        profile = {
            'input_dir': str(input_dir),
            'output_dir': str(output_dir),
            'exclude_exts': list(exclude_exts),
            'include_hidden': include_hidden,
            'recursive': recursive,
            'overwrite': overwrite,
            'compression_level': compression_level,
            'parallel': parallel,
            'quiet': quiet,
            'log_file': log_file,
            'format': format_type,
            'password': password,
            'split_size': split_size,
            'skip_incompressible': skip_incompressible,
            'min_size': min_size,
            'max_size': max_size,
            'after_date': after_date.isoformat() if after_date else None,
            'before_date': before_date.isoformat() if before_date else None,
            'include_pat': include_pat,
            'exclude_pat': exclude_pat,
            'dry_run': dry_run,
            'move_to_trash': move_to_trash,
            'compress_subdirs': compress_subdirs,
            'preserve_meta': preserve_meta,
            'process_archives': process_archives,
            'remove_original_after_conversion': remove_original_after_conversion
        }
        save_profile(profile)

    setup_logging(quiet, log_file)

    # ─── PROCESAR ARCHIVOS YA COMPRIMIDOS ──────────────────────────────────
    if process_archives and not dry_run:
        logger.info("Procesando archivos comprimidos existentes...")
        moved, converted, ahorro = process_existing_archives(
            input_dir, output_dir, format_type, recursive, include_hidden,
            overwrite, compression_level, password, remove_original_after_conversion
        )
        logger.info(f"Archivos movidos: {moved}, convertidos: {converted}")
        if ahorro > 0:
            logger.info(f"Ahorro total en conversión: {format_size(ahorro)}")

    # Recolectar archivos normales a comprimir
    if compress_subdirs:
        subdirs = [d for d in input_dir.iterdir() if d.is_dir() and (include_hidden or not d.name.startswith('.'))]
        if include_pat:
            subdirs = [d for d in subdirs if fnmatch.fnmatch(d.name, include_pat)]
        if exclude_pat:
            subdirs = [d for d in subdirs if not fnmatch.fnmatch(d.name, exclude_pat)]
        items_to_compress = subdirs
        logger.info(f"Se comprimirán {len(items_to_compress)} subdirectorio(s).")
    else:
        items_to_compress = collect_files(
            input_dir, recursive, include_hidden, exclude_exts, skip_incompressible,
            include_pat, exclude_pat, min_size, max_size, after_date, before_date,
            output_dir
        )
        logger.info(f"Se comprimirán {len(items_to_compress)} archivo(s).")

    if not items_to_compress:
        logger.info("No hay elementos para comprimir.")
        return

    if dry_run:
        logger.info("MODO SIMULACIÓN - se comprimirían los siguientes elementos:")
        for item in items_to_compress:
            logger.info(f"  {item.relative_to(input_dir)}")
        return

    # Compresión principal
    start_time = time.time()
    success_count = 0
    total_original = 0
    total_compressed = 0
    metadata_records = {}

    tasks = []
    for item in items_to_compress:
        if compress_subdirs:
            out_name = item.name + ('.zip' if format_type == 'zip' else '.tar.gz' if format_type == 'tar.gz' else '.7z')
            out_path = output_dir / out_name
            tasks.append((item, out_path, format_type, compression_level, overwrite, password, False))
        else:
            ext = item.suffix
            if format_type == 'zip':
                out_name = item.stem + ".zip"
            elif format_type == 'tar.gz':
                out_name = item.stem + ".tar.gz"
            elif format_type == '7z':
                out_name = item.stem + ".7z"
            out_path = output_dir / out_name
            tasks.append((item, out_path, format_type, compression_level, overwrite, password, split_size > 0))

    def process_task(task):
        item, out_path, fmt, level, ow, pwd, split_flag = task
        if compress_subdirs:
            return compress_file_subdir(item, out_path, fmt, level, ow, pwd)
        else:
            if fmt == 'zip':
                return compress_file_zip(item, out_path, level, ow, pwd, split_size)
            elif fmt == 'tar.gz':
                return compress_file_targz(item, out_path, ow)
            elif fmt == '7z':
                return compress_file_7z(item, out_path, ow, pwd)
            else:
                return (item.name, False, 0, 0, "formato no soportado")

    if parallel > 1:
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {executor.submit(process_task, task): task[0] for task in tasks}
            if TQDM_AVAILABLE and not quiet:
                pbar = tqdm(total=len(futures), desc="Comprimiendo", unit="elem")
            else:
                pbar = None
            for future in as_completed(futures):
                fname, ok, orig, comp, err = future.result()
                if ok:
                    success_count += 1
                    total_original += orig
                    total_compressed += comp
                    logger.info(f"✓ {fname} ({format_size(orig)} → {format_size(comp)})")
                    if preserve_meta and not compress_subdirs:
                        metadata_records[fname] = get_unix_metadata(task[0])
                    if move_to_trash and HAS_SEND2TRASH:
                        try:
                            send2trash(str(futures[future]))
                        except Exception as e:
                            logger.warning(f"No se pudo mover a papelera {fname}: {e}")
                else:
                    logger.warning(f"✗ {fname}: {err}")
                if pbar:
                    pbar.update(1)
            if pbar:
                pbar.close()
    else:
        if TQDM_AVAILABLE and not quiet:
            pbar = tqdm(tasks, desc="Comprimiendo", unit="elem")
        else:
            pbar = tasks
        for task in (pbar if TQDM_AVAILABLE else tasks):
            fname, ok, orig, comp, err = process_task(task)
            if ok:
                success_count += 1
                total_original += orig
                total_compressed += comp
                logger.info(f"✓ {fname} ({format_size(orig)} → {format_size(comp)})")
                if preserve_meta and not compress_subdirs:
                    metadata_records[fname] = get_unix_metadata(task[0])
                if move_to_trash and HAS_SEND2TRASH:
                    try:
                        send2trash(str(task[0]))
                    except Exception as e:
                        logger.warning(f"No se pudo mover a papelera {fname}: {e}")
            else:
                logger.warning(f"✗ {fname}: {err}")

    elapsed = time.time() - start_time

    if preserve_meta and metadata_records:
        meta_file = output_dir / "metadata_unix.json"
        try:
            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(metadata_records, f, indent=2)
            logger.info(f"Metadatos guardados en {meta_file}")
        except Exception as e:
            logger.warning(f"No se guardaron metadatos: {e}")

    # Resumen final (incluye los archivos movidos/convertidos si corresponde)
    print("\n" + "=" * 60)
    print("PROCESO COMPLETADO")
    print(f"Tiempo transcurrido: {format_time(elapsed)}")
    print(f"Elementos comprimidos (nuevos): {success_count}/{len(items_to_compress)}")
    if process_archives and not dry_run:
        print(f"Archivos movidos: {moved}, archivos convertidos: {converted}")
    if success_count > 0:
        print(f"Tamaño original total (nuevos): {format_size(total_original)}")
        print(f"Tamaño comprimido total (nuevos): {format_size(total_compressed)}")
        if total_original > 0:
            ratio = (1 - total_compressed / total_original) * 100
            print(f"Ahorro de espacio (nuevos): {ratio:.1f}%")
    print(f"Archivos de salida en: {output_dir}")
    if log_file:
        print(f"Registro guardado en: {log_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()