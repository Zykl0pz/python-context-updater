#!/usr/bin/env python3
# common.py - Rutas compartidas para todos los scripts del repositorio

import os
import sys
from pathlib import Path

def get_repo_root() -> Path:
    """
    Devuelve el directorio raíz del repositorio (donde se encuentra este archivo common.py).
    Siempre se resuelve la ruta real (sin enlaces simbólicos).
    """
    return Path(__file__).resolve().parent

# Directorios específicos (opcional, se pueden crear subcarpetas)
REPO_ROOT = get_repo_root()
LOGS_DIR = REPO_ROOT / "logs"
PROFILES_DIR = REPO_ROOT / "profiles"
OUTPUT_DIR = REPO_ROOT   # por defecto, los archivos de salida (context.md, packages.json) van aquí

def ensure_dirs():
    """Crea los directorios necesarios si no existen."""
    LOGS_DIR.mkdir(exist_ok=True)
    PROFILES_DIR.mkdir(exist_ok=True)

def get_log_path(log_filename: str) -> Path:
    """Devuelve la ruta completa para un archivo de log."""
    return LOGS_DIR / log_filename

def get_profile_path(profile_filename: str) -> Path:
    """Devuelve la ruta completa para un perfil JSON."""
    return PROFILES_DIR / profile_filename

def get_output_path(output_filename: str) -> Path:
    """Devuelve la ruta completa para un archivo de salida (context.md, etc.)."""
    return OUTPUT_DIR / output_filename