#!/usr/bin/env python3
"""
fix_migrations.py - Aplica los reemplazos de path_manager a los scripts del repositorio.
Corrige rutas de logs, perfiles y archivos de salida.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent

# Scripts a procesar (todos los .py excepto path_manager y este mismo)
SCRIPTS = [
    "context.py",
    "list_packages.py",
    "rename.py",
    "sort.py",
    "compress_to_path.py",
    "http_server.py",
    "start.py",
    "bootstrap.py",
]

# Diccionario de reemplazos por script: clave = script, valor = lista de tuplas (patrón regex, reemplazo)
REPLACEMENTS = {
    "context.py": [
        # Log
        (r"fh = logging\.FileHandler\('context\.log'",
         'fh = logging.FileHandler(str(get_log_path(__file__)))'),
        # Archivo .contextignore (global)
        (r"CONTEXTIGNORE_FILE\s*=\s*['\"]\.contextignore['\"]",
         'CONTEXTIGNORE_FILE = str(get_global_profile_path(__file__, ".contextignore"))'),
        # Perfil .context_profile.json
        (r"with open\('\.context_profile\.json', 'r'\) as f:",
         'with open(get_global_profile_path(__file__, ".context_profile.json"), "r") as f:'),
        (r"with open\('\.context_profile\.json', 'w'\) as f:",
         'with open(get_global_profile_path(__file__, ".context_profile.json"), "w") as f:'),
        # context_stats.json
        (r"with open\('context_stats\.json', 'w'",
         'with open(str(get_instance_dir(__file__) / "context_stats.json"), "w"'),
    ],
    "list_packages.py": [
        # Log
        (r"fh = logging\.FileHandler\('pkg_list\.log'",
         'fh = logging.FileHandler(str(get_log_path(__file__, "pkg_list.log")))'),
        # Perfil .pkg_profile.json en load_profile
        (r"def load_profile\(profile_path=\"\.pkg_profile\.json\"\):",
         'def load_profile(profile_path=None):\n    if profile_path is None:\n        profile_path = str(get_global_profile_path(__file__, ".pkg_profile.json"))'),
        # save_profile
        (r"save_profile\(profile, profile_path=\"\.pkg_profile\.json\"\)",
         'save_profile(profile, profile_path=str(get_global_profile_path(__file__, ".pkg_profile.json")))'),
    ],
    "rename.py": [
        (r"PROFILE_FILE\s*=\s*['\"]\.rename_profile\.json['\"]",
         'PROFILE_FILE = str(get_global_profile_path(__file__, ".rename_profile.json"))'),
        (r"RENAME_LOG\s*=\s*['\"]\.rename_history\.json['\"]",
         'RENAME_LOG = str(get_instance_dir(__file__) / ".rename_history.json")'),
    ],
    "sort.py": [
        (r"RENAME_LOG\s*=\s*['\"]\.rename_log\.json['\"]",
         'RENAME_LOG = str(get_instance_dir(__file__) / ".rename_log.json")'),
        (r"save_profile\(args, filename='\.sort_profile\.json'\)",
         'save_profile(args, filename=str(get_global_profile_path(__file__, ".sort_profile.json")))'),
    ],
    "compress_to_path.py": [
        (r"PROFILE_FILE\s*=\s*['\"]\.compress_profile\.json['\"]",
         'PROFILE_FILE = str(get_global_profile_path(__file__, ".compress_profile.json"))'),
        (r"log_file = input\(colored\(\"Nombre del archivo de log \[compresor\.log\]: \", Colors\.CYAN\)\)\.strip\(\) or \"compresor\.log\"",
         'log_file = input(colored("Nombre del archivo de log [compresor.log]: ", Colors.CYAN)).strip() or str(get_log_path(__file__, "compresor.log"))'),
    ],
    "start.py": [
        (r"LOG_FILE\s*=\s*REPO_DIR / \"start\.log\"",
         'LOG_FILE = get_log_path(__file__, "start.log")'),
    ],
    "bootstrap.py": [],  # No necesita cambios
    "http_server.py": [
        # Añadir log_path en CustomHandler y reemplazar log_message
        (r"class CustomHandler\(BaseHTTPRequestHandler\):",
         'class CustomHandler(BaseHTTPRequestHandler):\n    def __init__(self, *args, **kwargs):\n        self.log_path = get_instance_dir(__file__) / "http_server.log"\n        super().__init__(*args, **kwargs)'),
        (r"def log_message\(self, format, \*args\):",
         '    def log_message(self, format, *args):\n        try:\n            with open(self.log_path, "a", encoding="utf-8") as f:\n                f.write(f"[{self.log_date_time_string()}] {args[0]}\\n")\n        except:\n            pass\n        sys.stderr.write(f"[{self.log_date_time_string()}] {args[0]}\\n")'),
    ],
}

def backup_file(filepath: Path):
    """Crea una copia de seguridad .bak si no existe ya una."""
    backup = filepath.with_suffix(filepath.suffix + ".bak")
    if not backup.exists():
        import shutil
        shutil.copy2(filepath, backup)
        print(f"  Backup creado: {backup.name}")

def apply_replacements_to_file(script_path: Path):
    """Aplica los reemplazos definidos para el script."""
    if script_path.name not in REPLACEMENTS:
        print(f"⚠️  Sin reemplazos definidos para {script_path.name}")
        return False

    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    original = content
    for pattern, repl in REPLACEMENTS[script_path.name]:
        # Usar re.DOTALL para que . coincida con saltos de línea
        content = re.sub(pattern, repl, content, flags=re.DOTALL)

    if content == original:
        print(f"  No se realizaron cambios en {script_path.name}")
        return False

    backup_file(script_path)
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  ✅ Reemplazos aplicados en {script_path.name}")
    return True

def main():
    print("=== Aplicación de reemplazos de path_manager ===\n")
    modified = 0
    for script_name in SCRIPTS:
        script_path = REPO_ROOT / script_name
        if not script_path.exists():
            print(f"❌ {script_name} no encontrado, omitiendo.")
            continue
        print(f"📝 Procesando {script_name}...")
        if apply_replacements_to_file(script_path):
            modified += 1
    print(f"\n✅ {modified} archivo(s) modificado(s). Revise los cambios y elimine los .bak si todo funciona.")

if __name__ == "__main__":
    main()