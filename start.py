#!/usr/bin/env python3
"""
Lanzador principal del repositorio.
- Crea el entorno virtual (venv) si no existe.
- Instala las dependencias necesarias mostrando salida en vivo.
- Ejecuta cualquier script del directorio dentro del venv, con logs en tiempo real.
"""

import os
import sys
import subprocess
import venv
import platform
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# ─── Configuración ─────────────────────────────────────────────────────────
REPO_DIR = Path(__file__).parent.resolve()
VENV_DIR = REPO_DIR / "venv"
REQUIREMENTS_FILE = REPO_DIR / "requirements.txt"
LOG_FILE = REPO_DIR / "start.log"

# Dependencias necesarias (se pueden ajustar)
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

# Configuración de logging: archivo con timestamp y consola para errores
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stderr),  # errores en consola
    ],
)
logger = logging.getLogger("start")

def log_verbose(message: str, level: str = "info"):
    """Registra un mensaje en el log y opcionalmente lo imprime en consola."""
    if level == "info":
        logger.info(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "error":
        logger.error(message)
    else:
        logger.debug(message)
    # También imprimir en consola si no es error (ya lo hace StreamHandler)
    if level != "error":
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

def get_python_exe(venv_dir: Path) -> Path:
    if platform.system() == "Windows":
        return venv_dir / "Scripts" / "python.exe"
    else:
        return venv_dir / "bin" / "python"

def get_pip_exe(venv_dir: Path) -> Path:
    if platform.system() == "Windows":
        return venv_dir / "Scripts" / "pip.exe"
    else:
        return venv_dir / "bin" / "pip"

def create_venv_if_needed():
    if VENV_DIR.exists():
        log_verbose(f"✓ Entorno virtual ya existe en {VENV_DIR}")
        return
    log_verbose(f"📁 Creando entorno virtual en {VENV_DIR}...")
    try:
        venv.create(VENV_DIR, with_pip=True)
        log_verbose("✅ Entorno virtual creado correctamente.")
    except Exception as e:
        log_verbose(f"❌ Error al crear el entorno virtual: {e}", "error")
        sys.exit(1)

def ensure_requirements_file():
    if REQUIREMENTS_FILE.exists():
        log_verbose("✓ requirements.txt ya existe.")
        return
    log_verbose("📄 Generando requirements.txt con las dependencias necesarias...")
    try:
        with open(REQUIREMENTS_FILE, "w") as f:
            for dep in DEPENDENCIAS:
                f.write(dep + "\n")
        log_verbose("✅ requirements.txt creado.")
    except Exception as e:
        log_verbose(f"❌ Error al crear requirements.txt: {e}", "error")
        sys.exit(1)

def get_installed_packages(venv_dir: Path) -> List[str]:
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
        log_verbose(f"⚠️ No se pudo obtener lista de paquetes: {e}", "warning")
        return []

def install_missing_dependencies(venv_dir: Path):
    """
    Instala las dependencias faltantes mostrando la salida de pip en tiempo real
    (para ver velocidad y barra de progreso).
    """
    pip = get_pip_exe(venv_dir)
    installed = get_installed_packages(venv_dir)
    required = [dep.lower() for dep in DEPENDENCIAS]
    missing = [dep for dep in required if dep not in installed]

    if not missing:
        log_verbose("✓ Todas las dependencias ya están instaladas.")
        return

    log_verbose(f"📦 Instalando {len(missing)} dependencia(s) faltante(s):")
    for dep in missing:
        log_verbose(f"   - {dep}")
    log_verbose("🔄 Se mostrará el progreso de `pip` (velocidad incluida).")

    try:
        # Actualizar pip (muestra salida en tiempo real)
        log_verbose("⬆️  Actualizando pip...")
        subprocess.run([str(pip), "install", "--upgrade", "pip"], check=True)

        # Instalar dependencias con salida en vivo (no capturada)
        log_verbose("📥 Instalando dependencias...\n")
        subprocess.run(
            [str(pip), "install", "-r", str(REQUIREMENTS_FILE)],
            check=True,
            stdout=None,
            stderr=None,
        )
        log_verbose("✅ Todas las dependencias instaladas correctamente.")
    except subprocess.CalledProcessError as e:
        log_verbose(f"❌ Error durante la instalación: {e}", "error")
        sys.exit(1)

def run_script(script_path: str):
    """
    Ejecuta un script usando el intérprete del venv.
    La salida se muestra en tiempo real (no se captura).
    """
    python_exe = get_python_exe(VENV_DIR)
    full_script = REPO_DIR / script_path
    if not full_script.exists():
        log_verbose(f"❌ El script '{script_path}' no existe en {REPO_DIR}.", "error")
        sys.exit(1)

    log_verbose(f"🚀 Ejecutando {script_path} con el entorno virtual...")
    log_verbose(f"Comando: {python_exe} {full_script}")
    try:
        # Ejecutar en tiempo real (sin capturar)
        subprocess.run([str(python_exe), str(full_script)], check=True)
        log_verbose(f"✅ Script {script_path} finalizado correctamente.")
    except subprocess.CalledProcessError as e:
        log_verbose(f"⚠️ El script terminó con error (código {e.returncode}).", "warning")
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        log_verbose("\n🔴 Ejecución interrumpida por el usuario.", "warning")
        sys.exit(130)

def list_available_scripts() -> List[str]:
    """Devuelve una lista de archivos .py en el directorio (excluyendo este script)."""
    scripts = []
    for item in REPO_DIR.glob("*.py"):
        if item.name != Path(__file__).name:
            scripts.append(item.name)
    return sorted(scripts)

def interactive_menu():
    """Muestra un menú para seleccionar qué script ejecutar."""
    scripts = list_available_scripts()
    if not scripts:
        log_verbose("⚠️ No se encontraron scripts .py en el directorio.", "warning")
        return None

    print("\n" + "=" * 60)
    print("  📜 SCRIPTS DISPONIBLES EN EL REPOSITORIO")
    print("=" * 60)
    for idx, script in enumerate(scripts, start=1):
        print(f"  {idx}. {script}")
    print(f"  {len(scripts)+1}. Salir")
    opcion = input("\nSelecciona una opción: ").strip()
    if not opcion.isdigit():
        print("❌ Debes ingresar un número.")
        return None
    opcion = int(opcion)
    if 1 <= opcion <= len(scripts):
        return scripts[opcion - 1]
    elif opcion == len(scripts) + 1:
        return None
    else:
        print("❌ Opción inválida.")
        return None

def main():
    # Configuración inicial
    print("\n🐍 Inicializando entorno virtual...\n")
    create_venv_if_needed()
    ensure_requirements_file()
    install_missing_dependencies(VENV_DIR)

    # Decidir qué script ejecutar
    script_to_run = None
    if len(sys.argv) > 1:
        script_to_run = sys.argv[1]
        # Verificar que tiene extensión .py (opcional)
        if not script_to_run.endswith(".py"):
            script_to_run += ".py"
        log_verbose(f"Argumento recibido: {script_to_run}")
    else:
        print("\n✨ Entorno virtual listo. Mostrando menú interactivo...")
        script_to_run = interactive_menu()

    if script_to_run is None:
        log_verbose("👋 No se seleccionó ningún script. Saliendo.")
        sys.exit(0)

    # Ejecutar el script elegido
    run_script(script_to_run)

if __name__ == "__main__":
    main()