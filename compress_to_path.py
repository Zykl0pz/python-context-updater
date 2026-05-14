#!/usr/bin/env python3
"""
Comprime cada archivo individual en archivos ZIP separados.

Características:
- Interfaz interactiva por consola (sin argumentos en línea de comandos).
- Compresión en paralelo con ThreadPoolExecutor.
- Barra de progreso (tqdm) con fallback automático.
- Exclusión por extensión, archivos ocultos, vacíos y la propia salida.
- Modo recursivo, nivel de compresión configurable, sobrescritura opcional.
- Verificación de integridad de cada ZIP.
- Estadísticas finales (tamaño original/comprimido, tiempo, ahorro).
- Registro en archivo de log opcional.
"""

import os
import sys
import zipfile
import logging
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple

# Intenta importar tqdm, si no está disponible se usará un fallback simple
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

# ─── Colores ANSI (opcional) ──────────────────────────────────────────────
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

# ─── Configuración de logging ──────────────────────────────────────────────
logger = logging.getLogger('compresor')
logger.setLevel(logging.DEBUG)

# ─── Fallback si no hay tqdm ───────────────────────────────────────────────
def create_progress_bar(iterable, desc="", unit="", total=None):
    if TQDM_AVAILABLE:
        return tqdm(iterable, desc=desc, unit=unit, total=total)
    else:
        # Iterador simple con mensajes cada 10 archivos
        class SimpleProgress:
            def __init__(self, it, total_items, desc):
                self.it = iter(it)
                self.total = total_items
                self.desc = desc
                self.idx = 0
            def __iter__(self):
                return self
            def __next__(self):
                item = next(self.it)
                self.idx += 1
                if self.idx % 10 == 0 or self.idx == self.total:
                    print(f"{self.desc}: {self.idx}/{self.total}")
                return item
        return SimpleProgress(iterable, total, desc)

# ─── Funciones de compresión ───────────────────────────────────────────────
def compress_file(args: Tuple[Path, Path, int, bool]) -> Tuple[str, bool, int, int, str]:
    """
    Comprime un archivo individual y devuelve:
    (nombre, éxito, tamaño_original, tamaño_comprimido, mensaje_error)
    """
    file, output_dir, compress_level, overwrite = args
    zip_name = file.stem + ".zip"
    zip_path = output_dir / zip_name

    if zip_path.exists() and not overwrite:
        return (file.name, False, 0, 0, f"ya existe (omitido)")

    try:
        original_size = file.stat().st_size
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=compress_level) as zf:
            zf.write(file, arcname=file.name)
        # Verificar integridad del ZIP
        with zipfile.ZipFile(zip_path, 'r') as zf:
            bad_file = zf.testzip()
            if bad_file is not None:
                raise zipfile.BadZipFile(f"ZIP corrupto en archivo interno: {bad_file}")
        compressed_size = zip_path.stat().st_size
        return (file.name, True, original_size, compressed_size, "")
    except PermissionError as e:
        return (file.name, False, 0, 0, f"Permiso denegado: {e}")
    except OSError as e:
        return (file.name, False, 0, 0, f"Error de sistema: {e}")
    except Exception as e:
        return (file.name, False, 0, 0, str(e))

# ─── Interacción con el usuario ───────────────────────────────────────────
def prompt_yes_no(question, default="n"):
    """Pregunta sí/no (por defecto 'no')."""
    choices = " (s/n)" if default == "n" else " (S/n)"
    resp = input(colored(question + choices + ": ", Colors.CYAN)).strip().lower()
    if not resp:
        return default.lower() == "s"
    return resp in ('s', 'si', 'y', 'yes')

def prompt_int(question, default, min_val=None, max_val=None):
    """Pregunta un entero con validación."""
    while True:
        resp = input(colored(f"{question} [{default}]: ", Colors.CYAN)).strip()
        if not resp:
            return default
        try:
            val = int(resp)
            if (min_val is not None and val < min_val) or (max_val is not None and val > max_val):
                print(colored(f"El valor debe estar entre {min_val} y {max_val}.", Colors.WARNING))
                continue
            return val
        except ValueError:
            print(colored("Por favor, introduce un número entero.", Colors.WARNING))

def prompt_path(question, default="."):
    """Pregunta una ruta y la resuelve."""
    resp = input(colored(f"{question} [{default}]: ", Colors.CYAN)).strip()
    path = Path(resp).resolve() if resp else Path(default).resolve()
    return path

def prompt_extensions():
    """Pregunta extensiones a excluir (separadas por espacios)."""
    resp = input(colored("Extensiones a excluir (sin punto, separadas por espacio) [ninguna]: ", Colors.CYAN)).strip()
    if not resp:
        return set()
    # Limpiar y añadir punto si falta
    exts = {f".{ext.lstrip('.').lower()}" for ext in resp.split()}
    # Siempre excluimos .zip (para evitar reprocesamiento)
    exts.add(".zip")
    return exts

# ─── Función principal ────────────────────────────────────────────────────
def main():
    print(colored("\n=== COMPRESOR DE ARCHIVOS INDIVIDUALES ===", Colors.BOLD + Colors.HEADER))
    print("Este script comprimirá cada archivo en su propio ZIP dentro de la carpeta de salida.")

    # ─── Recoger configuración interactivamente ───
    input_dir = prompt_path("Directorio de entrada", ".")
    if not input_dir.is_dir():
        print(colored(f"El directorio {input_dir} no existe o no es válido.", Colors.FAIL))
        sys.exit(1)

    output_dir = prompt_path("Carpeta de salida para los ZIP", "comprimidos")
    try:
        output_dir.mkdir(exist_ok=True)
    except PermissionError:
        print(colored(f"Sin permisos para crear la carpeta de salida: {output_dir}", Colors.FAIL))
        sys.exit(1)

    # Exclusiones
    exclude_exts = prompt_extensions()
    # Siempre excluir el propio script
    script_name = Path(__file__).name

    include_hidden = prompt_yes_no("¿Incluir archivos ocultos (que empiezan con '.')?", "n")
    recursive = prompt_yes_no("¿Modo recursivo (incluir archivos en subdirectorios)?", "n")
    overwrite = prompt_yes_no("¿Sobrescribir ZIP existentes?", "n")
    compression_level = prompt_int("Nivel de compresión (0=sin comprimir, 9=máxima)", 8, 0, 9)
    parallel = prompt_int("Número de hilos para compresión en paralelo (1 = secuencial)", 1, 1, 16)
    quiet = prompt_yes_no("¿Modo silencioso (solo errores)?", "n")
    save_log = prompt_yes_no("¿Guardar registro detallado en archivo de log?", "n")
    log_file = None
    if save_log:
        log_file = input(colored("Nombre del archivo de log [compresor.log]: ", Colors.CYAN)).strip()
        if not log_file:
            log_file = "compresor.log"

    # Configurar logging final
    log_handlers = []
    if log_file:
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        log_handlers.append(fh)
    if not quiet:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter('%(message)s'))
        log_handlers.append(ch)
    else:
        # Solo errores en consola si es silencioso
        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(logging.WARNING)
        ch.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        log_handlers.append(ch)

    logger.handlers.clear()
    for handler in log_handlers:
        logger.addHandler(handler)

    # ─── Recoger archivos a comprimir ──────────────────────────────────────
    logger.info(colored(f"Analizando archivos en {input_dir}...", Colors.CYAN))

    files_to_compress = []
    pattern = "**/*" if recursive else "*"
    for entry in input_dir.glob(pattern):
        if not entry.is_file():
            continue
        # Excluir el propio script
        if entry.name == script_name:
            continue
        # Excluir extensiones
        if entry.suffix.lower() in exclude_exts:
            continue
        # Archivos ocultos
        if not include_hidden and entry.name.startswith('.'):
            continue
        # Archivos vacíos (se saltan)
        if entry.stat().st_size == 0:
            logger.info(f"Saltando archivo vacío: {entry.name}")
            continue
        # Evitar comprimir archivos que ya están dentro de la carpeta de salida
        try:
            if output_dir in entry.parents or entry.parent == output_dir:
                continue
        except ValueError:
            pass  # Posible error si están en discos distintos, no es grave
        files_to_compress.append(entry)

    if not files_to_compress:
        logger.info("No se encontraron archivos para comprimir.")
        return

    logger.info(f"Se comprimirán {len(files_to_compress)} archivo(s).")

    # Preparar tareas
    tasks = [(f, output_dir, compression_level, overwrite) for f in files_to_compress]

    start_time = time.time()
    success_count = 0
    total_original = 0
    total_compressed = 0

    # Barra de progreso con tqdm (si está) o fallback
    progress_desc = "Comprimiendo"
    if TQDM_AVAILABLE and not quiet:
        pbar = tqdm(total=len(tasks), desc=progress_desc, unit="archivo")
    else:
        pbar = create_progress_bar(tasks, desc=progress_desc, unit="archivo", total=len(tasks))

    if parallel > 1:
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {executor.submit(compress_file, task): task[0].name for task in tasks}
            for future in as_completed(futures):
                fname, ok, orig_sz, comp_sz, err = future.result()
                if ok:
                    success_count += 1
                    total_original += orig_sz
                    total_compressed += comp_sz
                    logger.info(f"✓ {fname} ({orig_sz} → {comp_sz} bytes)")
                else:
                    logger.warning(f"✗ {fname}: {err}")
                if TQDM_AVAILABLE and not quiet:
                    pbar.update(1)
                elif isinstance(pbar, tqdm):
                    pbar.update(1)
        if TQDM_AVAILABLE and not quiet:
            pbar.close()
    else:
        for task in tasks:
            fname, ok, orig_sz, comp_sz, err = compress_file(task)
            if ok:
                success_count += 1
                total_original += orig_sz
                total_compressed += comp_sz
                logger.info(f"✓ {fname} ({orig_sz} → {comp_sz} bytes)")
            else:
                logger.warning(f"✗ {fname}: {err}")
            if TQDM_AVAILABLE and not quiet:
                pbar.update(1)

    elapsed = time.time() - start_time

    # ─── Resumen final ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"Proceso completado en {elapsed:.2f} segundos.")
    print(f"Archivos comprimidos exitosamente: {success_count}/{len(files_to_compress)}")
    if success_count > 0:
        print(f"Tamaño original total: {total_original:,} bytes")
        print(f"Tamaño comprimido total: {total_compressed:,} bytes")
        if total_original > 0:
            ratio = (1 - total_compressed / total_original) * 100
            print(f"Ahorro de espacio: {ratio:.1f}%")
    print(f"Los ZIP se encuentran en: {output_dir}")
    if log_file:
        print(f"Registro detallado guardado en: {log_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()