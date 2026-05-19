#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Renombra archivos de forma interactiva: menú paso a paso.
Normaliza: minúsculas/casefold, espacios por '_', unicode opcional.
Resuelve colisiones globalmente, con detección de sistemas case‑insensitive.
Incluye modo --undo para deshacer el último renombrado.
"""

import json
import logging
import os
import re
import sys
import unicodedata
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional
from path_manager import get_repo_dir, get_script_dir, get_instance_dir, get_global_profile_path, get_log_path, get_cache_dir

# ─── Colores ANSI para terminal ────────────────────────────────────────────
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

# ─── Logging ───────────────────────────────────────────────────────────────
logger = logging.getLogger('renombrador_interactivo')
logging.basicConfig(format='%(message)s', level=logging.INFO)

# ─── Constantes ────────────────────────────────────────────────────────────
PROFILE_FILE = '.rename_profile.json'
RENAME_LOG = '.rename_history.json'  # archivo para deshacer cambios

# ─── Funciones de normalización y colisiones ───────────────────────────────
def obtener_archivos(
    directorio: Path,
    excluir_patrones: list[str],
    seguir_enlaces: bool = False,
) -> list[Path]:
    """Lista archivos a renombrar aplicando filtros."""
    script_ruta = Path(__file__).resolve()
    archivos = []
    for ruta in directorio.iterdir():
        if not ruta.is_file():
            continue
        if ruta.is_symlink() and not seguir_enlaces:
            logger.debug(f"Saltando enlace simbólico: {ruta.name}")
            continue
        try:
            if ruta.resolve() == script_ruta:
                logger.debug(f"Saltando el propio script: {ruta.name}")
                continue
        except OSError:
            pass
        nombre = ruta.name
        if any(fnmatch(nombre, patron) for patron in excluir_patrones):
            logger.debug(f"Excluido por patrón: {nombre}")
            continue
        archivos.append(ruta)
    return archivos

def normalizar_nombre(nombre: str, reemplazo: str = "_", normalizar_unicode: bool = False) -> str:
    """Genera nombre limpio: casefold, colapso de espacios, unicode opcional."""
    if normalizar_unicode:
        nombre = unicodedata.normalize("NFKD", nombre)
        nombre = nombre.encode("ascii", "ignore").decode("ascii")
    nombre = nombre.casefold()
    nombre = re.sub(r"\s+", reemplazo, nombre)
    nombre = nombre.strip(reemplazo)
    if not nombre:
        nombre = "archivo_sin_nombre"
    return nombre

def resolver_colisiones(
    mapeo: list[tuple[Path, str]],
    directorio: Path,
    max_intentos: int = 1000,
) -> dict[Path, Path]:
    """Planifica renombrados sin colisiones (incluye detección de case‑insensitive)."""
    rutas_originales = {orig for orig, _ in mapeo}
    ocupados = set()
    for ruta in directorio.iterdir():
        if ruta.is_file() and ruta not in rutas_originales:
            ocupados.add(ruta)

    resultado = {}
    for ruta_orig, nombre_deseado in sorted(mapeo, key=lambda x: x[0].name):
        extension_completa = "".join(ruta_orig.suffixes)
        candidato_nombre = nombre_deseado + extension_completa
        candidato = directorio / candidato_nombre
        intentos = 0
        while candidato in ocupados and not candidato.samefile(ruta_orig):
            intentos += 1
            if intentos > max_intentos:
                raise RuntimeError(f"Demasiados intentos para {ruta_orig.name}")
            nuevo_nombre = f"{nombre_deseado}_{intentos}{extension_completa}"
            candidato = directorio / nuevo_nombre
        ocupados.add(candidato)
        resultado[ruta_orig] = candidato
    return resultado

def renombrar_archivos(plan: dict[Path, Path], dry_run: bool = False) -> tuple[int, int, list[tuple[str, str]]]:
    """
    Ejecuta los renombrados.
    Retorna (éxitos, errores, lista de cambios exitosos como (origen, destino)).
    """
    exitos = errores = 0
    cambios = []
    for origen, destino in plan.items():
        if origen == destino:
            logger.info(f"Sin cambios: {origen.name}")
            continue
        try:
            if dry_run:
                logger.info(f"[SIMULACIÓN] {origen.name} -> {destino.name}")
            else:
                origen.rename(destino)
                logger.info(f"Renombrado: {origen.name} -> {destino.name}")
                cambios.append((str(origen), str(destino)))
            exitos += 1
        except Exception as e:
            logger.error(f"Error al renombrar {origen.name}: {e}")
            errores += 1
    return exitos, errores, cambios

# ─── Funciones de logging y deshacer ─────────────────────────────────────
def log_rename(log_path: str, changes: list[tuple[str, str]]) -> None:
    """Guarda la lista de renombrados en un JSON."""
    data = {
        'timestamp': datetime.now().isoformat(),
        'renames': [{'from': src, 'to': dst} for src, dst in changes]
    }
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(colored(f"Log de renombrado guardado en {log_path}", Colors.GREEN))

def undo_rename(log_path: str) -> None:
    """Deshace el último renombrado leyendo el log."""
    if not os.path.isfile(log_path):
        print(colored(f"No se encontró el log de deshacer ({log_path}).", Colors.FAIL))
        return
    with open(log_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    renames = data.get('renames', [])
    if not renames:
        print("El log está vacío.")
        return
    print(f"Deshaciendo {len(renames)} renombrados...")
    for entry in renames:
        src = entry['to']    # ahora existe como "to"
        dst = entry['from']  # nombre original
        try:
            Path(src).rename(Path(dst))
            print(f"Restaurado: {Path(src).name} -> {Path(dst).name}")
        except Exception as e:
            logger.error(f"Error al deshacer {src}: {e}")
    os.remove(log_path)
    print("Log eliminado.")

# ─── Menú interactivo ─────────────────────────────────────────────────────
def cargar_perfil() -> Optional[dict]:
    if Path(PROFILE_FILE).is_file():
        resp = input(colored(f"¿Cargar perfil guardado ({PROFILE_FILE})? (s/n) [s]: ", Colors.CYAN)).strip().lower()
        if resp in ('', 's', 'si'):
            try:
                with open(PROFILE_FILE, 'r', encoding='utf-8') as f:
                    perfil = json.load(f)
                print(colored("Perfil cargado.", Colors.GREEN))
                return perfil
            except Exception as e:
                logger.warning(f"No se pudo cargar el perfil: {e}")
    return None

def guardar_perfil(config: dict) -> None:
    try:
        with open(PROFILE_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(colored(f"Perfil guardado en {PROFILE_FILE}", Colors.GREEN))
    except Exception as e:
        logger.warning(f"No se pudo guardar el perfil: {e}")

def menu_configuracion() -> dict:
    """Recoge interactivamente todas las opciones y devuelve un diccionario."""
    print(colored("\n=== CONFIGURACIÓN DEL RENOMBRADOR ===", Colors.HEADER + Colors.BOLD))
    config = {}

    # Intentar cargar perfil existente
    perfil = cargar_perfil()
    if perfil:
        usar = input(colored("¿Usar la configuración del perfil? (s/n) [s]: ", Colors.CYAN)).strip().lower()
        if usar in ('', 's', 'si'):
            return perfil

    # 1. Directorio
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

    # 2. Carácter de reemplazo
    reemplazo = input(colored("Carácter para reemplazar espacios [ '_' ]: ", Colors.CYAN)).strip()
    config['replace'] = reemplazo if reemplazo else '_'

    # 3. Normalizar Unicode
    resp = input(colored("¿Normalizar caracteres Unicode a ASCII (quitar acentos)? (s/n) [n]: ", Colors.CYAN)).strip().lower()
    config['normalize'] = resp in ('s', 'si')

    # 4. Seguir enlaces simbólicos
    resp = input(colored("¿Procesar enlaces simbólicos a archivos? (s/n) [n]: ", Colors.CYAN)).strip().lower()
    config['follow_symlinks'] = resp in ('s', 'si')

    # 5. Patrones de exclusión
    config['exclude'] = []
    print(colored("Patrones de exclusión (estilo shell, ej. '*.tmp', '.*'). Dejar vacío para terminar.", Colors.BLUE))
    while True:
        patron = input(colored("Patrón (Enter=fin): ", Colors.CYAN)).strip()
        if not patron:
            break
        config['exclude'].append(patron)

    # 6. Modo simulación
    resp = input(colored("¿Ejecutar en modo simulación (dry-run)? (s/n) [n]: ", Colors.CYAN)).strip().lower()
    config['dry_run'] = resp in ('s', 'si')

    # 7. Límite de intentos para colisiones
    max_intentos_str = input(colored("Máximo de sufijos numéricos en colisión [1000]: ", Colors.CYAN)).strip()
    try:
        config['max_attempts'] = int(max_intentos_str) if max_intentos_str else 1000
    except ValueError:
        print(colored("Valor no válido, usando 1000.", Colors.WARNING))
        config['max_attempts'] = 1000

    # 8. Nivel de detalle
    print(colored("Nivel de detalle:", Colors.HEADER))
    print("1. Normal (solo cambios)")
    print("2. Silencioso (solo errores)")
    print("3. Detallado (más información)")
    while True:
        nivel = input(colored("Elige (1-3) [1]: ", Colors.CYAN)).strip()
        if nivel in ('', '1'):
            config['verbose'] = False
            config['quiet'] = False
            break
        elif nivel == '2':
            config['verbose'] = False
            config['quiet'] = True
            break
        elif nivel == '3':
            config['verbose'] = True
            config['quiet'] = False
            break
        else:
            print(colored("Opción no válida.", Colors.WARNING))

    # 9. Preguntar si desea guardar el perfil para el futuro
    guardar = input(colored("¿Guardar esta configuración como perfil? (s/n) [s]: ", Colors.CYAN)).strip().lower()
    if guardar in ('', 's', 'si'):
        guardar_perfil(config)

    return config

def mostrar_vista_previa(archivos, reemplazo, normalize):
    """Muestra qué archivos se renombrarán y cómo."""
    if not archivos:
        print(colored("No se encontraron archivos para renombrar.", Colors.WARNING))
        return
    print(colored("\n=== VISTA PREVIA ===", Colors.HEADER))
    print(f"{'Original':<40} {'Nuevo nombre'}")
    print("-" * 80)
    for ruta in archivos:
        nuevo_nombre_base = normalizar_nombre(ruta.stem, reemplazo, normalize)
        extension = "".join(ruta.suffixes)
        print(f"{ruta.name:<40} {nuevo_nombre_base + extension}")

def main() -> None:
    # ─── Modo deshacer ────────────────────────────────────
    if len(sys.argv) > 1 and sys.argv[1] == '--undo':
        undo_rename(RENAME_LOG)
        sys.exit(0)

    print(colored("Renombrador interactivo de archivos", Colors.BOLD))
    config = menu_configuracion()

    # Configurar logging según niveles elegidos
    if config.get('quiet'):
        logging.getLogger().setLevel(logging.ERROR)
    elif config.get('verbose'):
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    directorio = Path(config['directory']).resolve()
    reemplazo = config['replace']
    normalize = config['normalize']
    seguir_enlaces = config['follow_symlinks']
    excluir = config['exclude']
    dry_run = config['dry_run']
    max_intentos = config['max_attempts']

    # Obtener archivos
    try:
        archivos = obtener_archivos(directorio, excluir, seguir_enlaces)
    except Exception as e:
        logger.error(f"Error al listar archivos: {e}")
        sys.exit(1)

    if not archivos:
        logger.info("No se encontraron archivos para procesar.")
        sys.exit(0)

    # Mostrar vista previa siempre
    mostrar_vista_previa(archivos, reemplazo, normalize)

    # Confirmar ejecución si no es dry-run
    if not dry_run:
        confirm = input(colored("\n¿Aplicar estos cambios? (s/n) [s]: ", Colors.CYAN)).strip().lower()
        if confirm not in ('', 's', 'si'):
            print(colored("Operación cancelada.", Colors.WARNING))
            sys.exit(0)

    # Generar mapeo base
    mapeo_base = []
    for ruta in archivos:
        nuevo_nombre_base = normalizar_nombre(ruta.stem, reemplazo, normalize)
        mapeo_base.append((ruta, nuevo_nombre_base))

    # Resolver colisiones
    try:
        plan = resolver_colisiones(mapeo_base, directorio, max_intentos)
    except Exception as e:
        logger.error(f"Error planificando: {e}")
        sys.exit(1)

    # Ejecutar (o simular)
    exitos, errores, cambios = renombrar_archivos(plan, dry_run=dry_run)

    # Guardar log si hubo cambios reales
    if cambios and not dry_run:
        log_rename(RENAME_LOG, cambios)

    # Resumen
    print(colored("\n--- RESUMEN ---", Colors.BOLD))
    print(f"Renombrados: {exitos}")
    if errores:
        print(colored(f"Errores: {errores}", Colors.FAIL))
    if exitos == 0 and errores == 0:
        print("Todos los archivos ya tenían el nombre deseado.")
    if dry_run:
        print("(modo simulación: no se realizaron cambios reales)")

if __name__ == "__main__":
    main()