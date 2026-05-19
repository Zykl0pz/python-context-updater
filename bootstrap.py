#!/usr/bin/env python3
"""
Script de inicio para el repositorio de herramientas.
- Crea un entorno virtual (venv) en la carpeta del proyecto si no existe.
- Verifica que todas las dependencias están instaladas dentro del venv.
- Si faltan, las instala automáticamente desde requirements.txt (o lo genera si no existe).
- Finalmente, ofrece un menú interactivo para ejecutar los scripts usando el intérprete del venv.
"""

import os
import sys
import subprocess
import venv
import platform
import json
import importlib.util
from pathlib import Path
from typing import List, Tuple, Optional

# ─── Configuración ─────────────────────────────────────────────────────────
REPO_DIR = Path(__file__).parent.resolve()  # Directorio donde está este script
VENV_DIR = REPO_DIR / "venv"
REQUIREMENTS_FILE = REPO_DIR / "requirements.txt"

# Lista de dependencias principales (se pueden agregar más)
DEPENDENCIAS = [
    "tqdm",
    "charset-normalizer",
    "pathspec",
    "py7zr",
    "pyzipper",
    "send2trash",
    "PyPDF2",
    "pdfplumber",
]

# Scripts del repositorio que se pueden ejecutar (ruta relativa y nombre para mostrar)
SCRIPTS = [
    ("context.py", "Generador de contexto de código"),
    ("list_packages.py", "Listado de paquetes instalados"),
    ("rename.py", "Renombrador interactivo de archivos"),
    ("sort.py", "Ordenar y renombrar con índice"),
    ("compress_to_path.py", "Compresor/descompresor interactivo"),
    ("http_server.py", "Servidor HTTP con interfaz web"),
]

# ─── Funciones auxiliares ──────────────────────────────────────────────────
def get_python_exe(venv_dir: Path) -> Path:
    """Devuelve la ruta al ejecutable de Python dentro del venv."""
    if platform.system() == "Windows":
        return venv_dir / "Scripts" / "python.exe"
    else:
        return venv_dir / "bin" / "python"

def get_pip_exe(venv_dir: Path) -> Path:
    """Devuelve la ruta al ejecutable de pip dentro del venv."""
    if platform.system() == "Windows":
        return venv_dir / "Scripts" / "pip.exe"
    else:
        return venv_dir / "bin" / "pip"

def create_venv_if_needed():
    """Crea el entorno virtual si no existe."""
    if not VENV_DIR.exists():
        print(f"📁 Creando entorno virtual en {VENV_DIR}...")
        try:
            venv.create(VENV_DIR, with_pip=True)
            print("✅ Entorno virtual creado correctamente.")
        except Exception as e:
            print(f"❌ Error al crear el entorno virtual: {e}")
            sys.exit(1)
    else:
        print(f"✓ Entorno virtual ya existe en {VENV_DIR}.")

def ensure_requirements_file():
    """Genera requirements.txt si no existe, basado en DEPENDENCIAS."""
    if not REQUIREMENTS_FILE.exists():
        print("📄 Generando requirements.txt con las dependencias necesarias...")
        try:
            with open(REQUIREMENTS_FILE, "w") as f:
                for dep in DEPENDENCIAS:
                    f.write(dep + "\n")
            print("✅ requirements.txt creado.")
        except Exception as e:
            print(f"❌ Error al crear requirements.txt: {e}")
            sys.exit(1)
    else:
        print("✓ requirements.txt ya existe.")

def get_installed_packages(venv_dir: Path) -> List[str]:
    """Devuelve una lista de nombres de paquetes instalados en el venv."""
    pip = get_pip_exe(venv_dir)
    try:
        result = subprocess.run(
            [str(pip), "list", "--format=json"],
            capture_output=True,
            text=True,
            check=True,
        )
        packages = json.loads(result.stdout)
        return [pkg["name"].lower() for pkg in packages]
    except Exception as e:
        print(f"⚠️ No se pudo obtener la lista de paquetes instalados: {e}")
        return []

def install_missing_dependencies(venv_dir: Path):
    """Instala las dependencias faltantes usando pip."""
    pip = get_pip_exe(venv_dir)
    installed = get_installed_packages(venv_dir)
    required = [dep.lower() for dep in DEPENDENCIAS]
    missing = [dep for dep in required if dep not in installed]

    if missing:
        print(f"📦 Instalando dependencias faltantes: {', '.join(missing)}...")
        try:
            subprocess.run(
                [str(pip), "install", "--upgrade", "pip"],  # Actualizar pip primero
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [str(pip), "install", "-r", str(REQUIREMENTS_FILE)],
                check=True,
                capture_output=True,
                text=True,
            )
            print("✅ Todas las dependencias instaladas correctamente.")
        except subprocess.CalledProcessError as e:
            print(f"❌ Error al instalar dependencias: {e}")
            if e.stderr:
                print(f"Detalle: {e.stderr}")
            sys.exit(1)
    else:
        print("✓ Todas las dependencias ya están instaladas.")

def run_script_with_venv(script_rel_path: str):
    """Ejecuta un script usando el intérprete del venv."""
    python_exe = get_python_exe(VENV_DIR)
    script_path = REPO_DIR / script_rel_path
    if not script_path.exists():
        print(f"❌ El script {script_rel_path} no existe en el repositorio.")
        return
    print(f"\n🚀 Ejecutando {script_rel_path} con el entorno virtual...\n")
    try:
        subprocess.run([str(python_exe), str(script_path)], check=True)
    except subprocess.CalledProcessError as e:
        print(f"⚠️ El script terminó con error (código {e.returncode}).")
    except KeyboardInterrupt:
        print("\n🔴 Ejecución interrumpida por el usuario.")
    input("\nPresiona Enter para volver al menú...")

def mostrar_menu():
    """Muestra el menú principal y maneja la selección."""
    while True:
        print("\n" + "=" * 60)
        print("  🛠️  MENÚ DE HERRAMIENTAS (entorno virtual activo)  ")
        print("=" * 60)
        for idx, (_, desc) in enumerate(SCRIPTS, start=1):
            print(f"  {idx}. {desc}")
        print(f"  {len(SCRIPTS)+1}. Salir")
        opcion = input("\nSelecciona una opción: ").strip()
        if not opcion.isdigit():
            print("❌ Por favor ingresa un número.")
            continue
        opcion = int(opcion)
        if 1 <= opcion <= len(SCRIPTS):
            script_name, _ = SCRIPTS[opcion - 1]
            run_script_with_venv(script_name)
        elif opcion == len(SCRIPTS) + 1:
            print("👋 ¡Hasta luego!")
            break
        else:
            print("❌ Opción inválida.")

# ─── Punto de entrada principal ────────────────────────────────────────────
def main():
    print("🐍 Inicializando el entorno virtual del repositorio...")
    create_venv_if_needed()
    ensure_requirements_file()
    install_missing_dependencies(VENV_DIR)
    print("\n✨ Entorno virtual listo y verificado.\n")
    mostrar_menu()

if __name__ == "__main__":
    main()