#!/usr/bin/env python3
"""
fix_paths.py - Modifica los scripts del repositorio para que guarden logs, perfiles y salidas
dentro de la raíz del repositorio (usando common.py).
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent
COMMON_IMPORT = "import common\n"

# Lista de scripts a modificar (excluimos common.py y este script)
SCRIPTS = [
    "context.py",
    "list_packages.py",
    "rename.py",
    "sort.py",
    "compress_to_path.py",
    "http_server.py",
]

# Diccionario con patrones de búsqueda y reemplazo
# (clave = nombre del script, valor = lista de tuplas (buscar, reemplazar))
CHANGES = {
    "context.py": [
        # Logging
        (r"logging\.FileHandler\('context\.log'", r"logging.FileHandler(str(common.get_log_path('context.log')))"),
        # .contextignore
        (r"CONTEXTIGNORE_FILE = '\.contextignore'", r"CONTEXTIGNORE_FILE = common.REPO_ROOT / '.contextignore'"),
        # load_contextignore: cambiar la ruta por defecto
        (r"def load_contextignore\(start_path='\.'\):", r"def load_contextignore(start_path=None):"),
        (r"path = os\.path\.join\(start_path, CONTEXTIGNORE_FILE\)", r"path = CONTEXTIGNORE_FILE if start_path is None else os.path.join(start_path, CONTEXTIGNORE_FILE.name)"),
        # Perfil
        (r"\.context_profile\.json", r"common.get_profile_path('.context_profile.json')"),
        # Archivos de salida
        (r"'context\.md'", r"str(common.get_output_path('context.md'))"),
        (r"'context\.json'", r"str(common.get_output_path('context.json'))"),
        (r"'context\.xml'", r"str(common.get_output_path('context.xml'))"),
        (r"'context\.txt'", r"str(common.get_output_path('context.txt'))"),
        (r"'context_stats\.json'", r"str(common.get_output_path('context_stats.json'))"),
    ],
    "list_packages.py": [
        (r"logging\.FileHandler\('pkg_list\.log'", r"logging.FileHandler(str(common.get_log_path('pkg_list.log')))"),
        (r"PROFILE_FILE = '\.pkg_profile\.json'", r"PROFILE_FILE = common.get_profile_path('.pkg_profile.json')"),
        (r"'packages\.md'", r"str(common.get_output_path('packages.md'))"),
        (r"'packages\.json'", r"str(common.get_output_path('packages.json'))"),
        (r"'packages\.xml'", r"str(common.get_output_path('packages.xml'))"),
        (r"'packages\.txt'", r"str(common.get_output_path('packages.txt'))"),
        (r"'packages_stats\.json'", r"str(common.get_output_path('packages_stats.json'))"),
        (r"'pkgs\.md'", r"str(common.get_output_path('pkgs.md'))"),
    ],
    "rename.py": [
        (r"PROFILE_FILE = '\.rename_profile\.json'", r"PROFILE_FILE = common.get_profile_path('.rename_profile.json')"),
        (r"RENAME_LOG = '\.rename_history\.json'", r"RENAME_LOG = common.get_log_path('rename_history.json')"),
    ],
    "sort.py": [
        (r"RENAME_LOG = '\.rename_log\.json'", r"RENAME_LOG = common.get_log_path('sort_rename_log.json')"),
        (r"filename='\.sort_profile\.json'", r"filename=str(common.get_profile_path('.sort_profile.json'))"),
    ],
    "compress_to_path.py": [
        (r"PROFILE_FILE = '\.compress_profile\.json'", r"PROFILE_FILE = common.get_profile_path('.compress_profile.json')"),
        (r"log_file = 'compresor\.log'", r"log_file = str(common.get_log_path('compresor.log'))"),
    ],
    "http_server.py": [
        # No hay cambios necesarios
    ],
}

def apply_changes():
    # Asegurarse de que common.py existe
    common_file = REPO_ROOT / "common.py"
    if not common_file.exists():
        print("❌ No se encuentra common.py. Créalo primero.")
        return

    for script in SCRIPTS:
        script_path = REPO_ROOT / script
        if not script_path.exists():
            print(f"⚠️ {script} no encontrado, saltando.")
            continue

        print(f"📝 Procesando {script}...")
        with open(script_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Añadir import common si no está presente
        if "import common" not in content:
            # Buscar la primera línea no comentario para insertar después
            lines = content.splitlines()
            insert_pos = 0
            for i, line in enumerate(lines):
                if line.strip() and not line.strip().startswith("#"):
                    insert_pos = i
                    break
            lines.insert(insert_pos + 1, COMMON_IMPORT.strip())
            content = "\n".join(lines)

        # Aplicar los reemplazos específicos
        for old, new in CHANGES.get(script, []):
            content = re.sub(old, new, content)

        # Asegurar que common.REPO_ROOT esté disponible (agregar al inicio si es necesario)
        if "common.REPO_ROOT" in content and "common.ensure_dirs()" not in content:
            # Insertar common.ensure_dirs() cerca del inicio del main
            content = re.sub(
                r"(def main\(\):.*?)(\n    )",
                r"\1\n    common.ensure_dirs()\n    ",
                content,
                flags=re.DOTALL,
            )

        with open(script_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ {script} modificado.")

    print("\n🎉 Todos los scripts han sido actualizados. Ahora guardarán logs y perfiles dentro del repositorio.")

if __name__ == "__main__":
    apply_changes()