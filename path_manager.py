#!/usr/bin/env python3
"""
Gestor de rutas para los scripts del repositorio.
Todos los archivos generados (logs, perfiles, caché) se guardan en:
    <repo_dir>/output/<script_name>/<cwd_path_safe>/
donde <cwd_path_safe> es el directorio de trabajo actual convertido a una ruta válida.
"""

import os
import sys
from pathlib import Path

def get_repo_dir() -> Path:
    """Devuelve la raíz del repositorio (donde está este módulo)."""
    return Path(__file__).parent.resolve()

def get_script_dir(script_file: str) -> Path:
    """
    Devuelve el directorio específico para un script.
    Ahora dentro de la carpeta 'output' en la raíz del repositorio.
    Por ejemplo, para 'context.py' devuelve <repo>/output/context/
    """
    repo = get_repo_dir()
    script_name = Path(script_file).stem  # sin extensión
    output_dir = repo / "output" / script_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir

def get_cwd_safe() -> str:
    """
    Convierte el directorio de trabajo actual en una cadena segura para nombres de carpeta.
    Reemplaza '/' y '\\' por '_', y elimina caracteres problemáticos.
    """
    cwd = Path.cwd().resolve()
    # Reemplazar separadores y eliminar ':' en Windows (unidades)
    safe = str(cwd).replace(os.sep, '_').replace(':', '')
    # Limitar longitud (opcional)
    if len(safe) > 200:
        safe = safe[:200]
    return safe

def get_instance_dir(script_file: str) -> Path:
    """
    Devuelve el directorio de instancia para este script y el directorio de trabajo actual.
    Ejemplo: <repo>/output/context/<cwd_safe>/
    """
    script_dir = get_script_dir(script_file)
    instance = script_dir / get_cwd_safe()
    instance.mkdir(parents=True, exist_ok=True)
    return instance

def get_profile_path(script_file: str, profile_name: str = ".profile.json") -> Path:
    """
    Ruta para un archivo de perfil.
    Por defecto se guarda en <repo>/output/<script_name>/<cwd_safe>/<profile_name>.
    Si se desea un perfil global (compartido para todas las ejecuciones), usar get_global_profile_path.
    """
    inst = get_instance_dir(script_file)
    return inst / profile_name

def get_global_profile_path(script_file: str, profile_name: str = ".profile.json") -> Path:
    """
    Ruta para un perfil global (compartido entre todas las ejecuciones).
    Se guarda en <repo>/output/<script_name>/global/<profile_name>.
    """
    script_dir = get_script_dir(script_file)
    global_dir = script_dir / "global"
    global_dir.mkdir(parents=True, exist_ok=True)
    return global_dir / profile_name

def get_log_path(script_file: str, log_name: str = None) -> Path:
    """Ruta para un archivo de log."""
    if log_name is None:
        log_name = f"{Path(script_file).stem}.log"
    inst = get_instance_dir(script_file)
    return inst / log_name

def get_cache_dir(script_file: str) -> Path:
    """Directorio para caché (por ejemplo, encoding cache)."""
    inst = get_instance_dir(script_file)
    cache_dir = inst / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir