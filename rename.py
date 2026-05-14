#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Renombra archivos en un directorio siguiendo reglas configurables:
- Todo a minúsculas (casefold) y espacios/espacios en blanco por '_'.
- Colisión de nombres resuelta globalmente (sin sufijos innecesarios).
- Opción de normalizar Unicode (NFKD → ASCII).
- Interfaz de línea de comandos completa.
- Usa pathlib para mayor claridad y robustez.
"""

import argparse
import logging
import re
import sys
import unicodedata
from fnmatch import fnmatch
from pathlib import Path

# ----------------------------------------------------------------------
# Configuración del logger
# ----------------------------------------------------------------------
logger = logging.getLogger("renombrador")
logging.basicConfig(format="%(message)s", level=logging.WARNING)  # ajustable con -v/-q


# ----------------------------------------------------------------------
# Funciones auxiliares
# ----------------------------------------------------------------------
def obtener_archivos(
    directorio: Path,
    excluir_patrones: list[str],
    seguir_enlaces: bool = False,
) -> list[Path]:
    """
    Lista los archivos del directorio que pueden renombrarse,
    excluyendo el propio script, directorios, enlaces (opcional) y
    archivos que coincidan con algún patrón de exclusión.
    """
    script_ruta = Path(__file__).resolve()
    archivos = []
    for ruta in directorio.iterdir():
        # 1. Solo archivos (excluir directorios)
        if not ruta.is_file():
            continue

        # 13. Ignorar enlaces simbólicos si no se indica lo contrario
        if ruta.is_symlink() and not seguir_enlaces:
            logger.debug(f"Saltando enlace simbólico: {ruta.name}")
            continue

        # Excluir el propio script
        try:
            if ruta.resolve() == script_ruta:
                logger.debug(f"Saltando el script: {ruta.name}")
                continue
        except OSError:
            # Si no se puede resolver, asumir que no es el script
            pass

        # Patrones de exclusión (estilo shell)
        nombre = ruta.name
        if any(fnmatch(nombre, patron) for patron in excluir_patrones):
            logger.debug(f"Excluido por patrón: {nombre}")
            continue

        archivos.append(ruta)

    return archivos


def normalizar_nombre(
    nombre: str,
    reemplazo: str = "_",
    normalizar_unicode: bool = False,
) -> str:
    """
    Genera un nuevo nombre aplicando:
    - Normalización Unicode opcional (NFKD → ASCII).
    - Casefold (más agresivo que lower, p.ej. 'ß' -> 'ss').
    - Colapsa cualquier secuencia de caracteres de espacio/blanco (\s+)
      en el carácter de reemplazo.
    - Elimina guiones bajos al inicio y final.
    """
    if normalizar_unicode:
        # Descomponer y eliminar diacríticos, pasar a ASCII
        nombre = unicodedata.normalize("NFKD", nombre)
        nombre = nombre.encode("ascii", "ignore").decode("ascii")

    # Casefold para lowercase agresivo
    nombre = nombre.casefold()

    # Reemplazar cualquier secuencia de espacios (incluye tabs, saltos) por '_'
    nombre = re.sub(r"\s+", reemplazo, nombre)

    # Limpiar guiones bajos sobrantes en extremos
    nombre = nombre.strip(reemplazo)

    # Si el nombre queda vacío, asignar un nombre por defecto
    if not nombre:
        nombre = "archivo_sin_nombre"

    return nombre


def resolver_colisiones(
    mapeo: list[tuple[Path, str]],
    directorio: Path,
    max_intentos: int = 1000,
) -> dict[Path, Path]:
    """
    A partir de una lista de (ruta_original, nombre_deseado),
    asigna nuevos nombres sin colisiones reales entre sí ni con archivos
    existentes no implicados en el renombrado.
    Retorna un diccionario {ruta_original: nueva_ruta}.
    """
    # Conjunto de rutas ocupadas: archivos actuales que NO están en la lista
    # de originales (así permitimos renombrar un archivo cambiando solo mayúsculas)
    rutas_originales = {orig for orig, _ in mapeo}
    ocupados = set()
    for ruta in directorio.iterdir():
        if ruta.is_file() and ruta not in rutas_originales:
            ocupados.add(ruta)
        # También se ignoran enlaces si no se van a procesar (ya filtrados)

    resultado = {}
    # Procesar en orden predecible (alfabético por nombre original)
    for ruta_orig, nombre_deseado in sorted(mapeo, key=lambda x: x[0].name):
        base = ruta_orig.stem  # nombre sin extensión
        # Obtener la extensión completa (p. ej. ".tar.gz")
        extension_completa = "".join(ruta_orig.suffixes)
        candidato_nombre = nombre_deseado + extension_completa
        candidato = directorio / candidato_nombre

        intentos = 0
        # 1. Evitar falsa colisión por case-insensitivity (mejora 1)
        # Si el candidato existe pero es el mismo archivo (cambio de capitalización),
        # no consideramos colisión.
        while candidato in ocupados and not candidato.samefile(ruta_orig):
            intentos += 1
            if intentos > max_intentos:
                raise RuntimeError(
                    f"Demasiados intentos de renombre para {ruta_orig.name}"
                )
            # Añadir sufijo numérico antes de la extensión
            nuevo_nombre = f"{nombre_deseado}_{intentos}{extension_completa}"
            candidato = directorio / nuevo_nombre

        # Si el candidato es el mismo archivo (rename solo cambia capitalización),
        # se permite; no se añade a ocupados porque ya estará reemplazado.
        ocupados.add(candidato)
        resultado[ruta_orig] = candidato

    return resultado


def renombrar_archivos(
    plan: dict[Path, Path],
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Ejecuta los renombrados según el plan.
    Retorna (número de éxitos, número de errores).
    """
    exitos = 0
    errores = 0
    for origen, destino in plan.items():
        if origen == destino:
            logger.info(f"Sin cambios (nombre normalizado idéntico): {origen.name}")
            continue
        try:
            if dry_run:
                logger.info(f"[SIMULACIÓN] {origen.name} -> {destino.name}")
            else:
                origen.rename(destino)
                logger.info(f"Renombrado: {origen.name} -> {destino.name}")
            exitos += 1
        except Exception as e:
            logger.error(f"Error al renombrar {origen.name}: {e}")
            errores += 1
    return exitos, errores


# ----------------------------------------------------------------------
# Configuración de línea de comandos (argparse)
# ----------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Renombra archivos: minúsculas, espacios por '_', y más."
    )
    parser.add_argument(
        "-d", "--directory",
        type=Path,
        default=Path.cwd(),
        help="Directorio a procesar (por defecto: directorio actual)",
    )
    parser.add_argument(
        "-r", "--replace",
        default="_",
        help="Carácter para reemplazar espacios en blanco (defecto: '_')",
    )
    parser.add_argument(
        "-e", "--exclude",
        action="append",
        default=[],
        help="Patrones de exclusión (estilo shell), se puede repetir (ej.: -e '*.tmp' -e '.*')",
    )
    parser.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Muestra qué se haría sin modificar nada",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Muestra más información (nivel INFO)",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Solo muestra errores (nivel ERROR)",
    )
    parser.add_argument(
        "--follow-symlinks",
        action="store_true",
        help="Procesar también enlaces simbólicos a archivos",
    )
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="Normaliza caracteres Unicode (NFKD) a ASCII (elimina acentos, ñ->n, etc.)",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=1000,
        help="Límite de intentos para evitar bucles infinitos en colisiones",
    )
    return parser.parse_args()


# ----------------------------------------------------------------------
# Principal
# ----------------------------------------------------------------------
def main() -> None:
    args = parse_args()

    # Configurar nivel de logging
    if args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
    elif args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    elif args.dry_run:
        logging.getLogger().setLevel(logging.INFO)  # siempre mostrar simulación

    directorio = args.directory.resolve()

    if not directorio.is_dir():
        logger.error(f"El directorio no existe: {directorio}")
        sys.exit(1)

    logger.info(f"Directorio: {directorio}")
    if args.dry_run:
        logger.info("*** MODO SIMULACIÓN (--dry-run) ***")

    # 1. Obtener archivos a procesar
    try:
        archivos = obtener_archivos(
            directorio,
            args.exclude,
            seguir_enlaces=args.follow_symlinks,
        )
    except Exception as e:
        logger.error(f"Error al listar archivos: {e}")
        sys.exit(1)

    if not archivos:
        logger.info("No se encontraron archivos para procesar.")
        sys.exit(0)

    logger.info(f"Archivos candidatos: {len(archivos)}")

    # 2. Generar nombres normalizados (mapeo original -> nombre base deseado)
    mapeo_base = []
    for ruta in archivos:
        nombre_original = ruta.stem  # sin extensión
        nuevo_nombre = normalizar_nombre(
            nombre_original,
            reemplazo=args.replace,
            normalizar_unicode=args.normalize,
        )
        mapeo_base.append((ruta, nuevo_nombre))

    # 3. Resolver colisiones globalmente
    try:
        plan = resolver_colisiones(
            mapeo_base,
            directorio,
            max_intentos=args.max_attempts,
        )
    except Exception as e:
        logger.error(f"Error al planificar renombrados: {e}")
        sys.exit(1)

    # 4. Ejecutar (o simular)
    exitos, errores = renombrar_archivos(plan, dry_run=args.dry_run)

    # 5. Resumen final
    logger.info("--- Resumen ---")
    logger.info(f"Renombrados: {exitos}")
    if errores:
        logger.error(f"Errores: {errores}")
    if exitos == 0 and errores == 0:
        logger.info("Todos los archivos ya tenían el nombre deseado.")
    if args.dry_run:
        logger.info("(no se realizaron cambios reales)")


if __name__ == "__main__":
    main()