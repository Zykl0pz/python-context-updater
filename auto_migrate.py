#!/usr/bin/env python3
"""
Script de automatización para migrar los scripts del repositorio a usar path_manager.
- Crea path_manager.py si no existe.
- Añade las importaciones necesarias.
- Reemplaza rutas fijas de logs, perfiles y caché por las funciones de path_manager.
- Realiza copias de seguridad (.bak) de los archivos modificados.
"""

import os
import re
import sys
import shutil
from pathlib import Path
from typing import List, Tuple

# ─── Configuración ─────────────────────────────────────────────────────────
REPO_DIR = Path(__file__).parent.resolve()
BACKUP_SUFFIX = ".bak"

# Archivos a excluir de la migración
EXCLUDE_FILES = {
    "path_manager.py",
    "auto_migrate.py",
}

# Contenido del módulo path_manager (debe ser el mismo que se mostró antes)
PATH_MANAGER_CONTENT = '''#!/usr/bin/env python3
"""
Gestor de rutas para los scripts del repositorio.
Todos los archivos generados (logs, perfiles, caché) se guardan en:
    <repo_dir>/<script_name>/<cwd_path_safe>/
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
    Por ejemplo, para 'context.py' devuelve <repo>/context/
    """
    repo = get_repo_dir()
    script_name = Path(script_file).stem  # sin extensión
    return repo / script_name

def get_cwd_safe() -> str:
    """
    Convierte el directorio de trabajo actual en una cadena segura para nombres de carpeta.
    Reemplaza '/' y '\\\\' por '_', y elimina caracteres problemáticos.
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
    Ejemplo: <repo>/context/<cwd_safe>/
    """
    script_dir = get_script_dir(script_file)
    instance = script_dir / get_cwd_safe()
    instance.mkdir(parents=True, exist_ok=True)
    return instance

def get_profile_path(script_file: str, profile_name: str = ".profile.json") -> Path:
    """
    Ruta para un archivo de perfil.
    Por defecto se guarda en <repo>/<script_name>/<cwd_safe>/<profile_name>.
    Si se desea un perfil global (compartido para todas las ejecuciones), usar get_global_profile_path.
    """
    inst = get_instance_dir(script_file)
    return inst / profile_name

def get_global_profile_path(script_file: str, profile_name: str = ".profile.json") -> Path:
    """
    Ruta para un perfil global (compartido entre todas las ejecuciones).
    Se guarda en <repo>/<script_name>/global/<profile_name>.
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
'''

# ─── Mapeo de reemplazos para cada script ──────────────────────────────────
# Cada entrada: (nombre_script, lista_de_reemplazos)
# Los reemplazos son tuplas (buscar, reemplazar) donde buscar puede ser regex o string.
# También se puede especificar una función de transformación.

REPLACEMENTS = {
    "context.py": [
        # Perfil global
        (r"CONTEXTIGNORE_FILE\s*=\s*['\"]\.contextignore['\"]",
         'CONTEXTIGNORE_FILE = str(get_global_profile_path(__file__, ".contextignore"))'),
        (r"load_profile\(\)",
         'load_profile()'),
        (r"save_profile\(profile\)",
         'save_profile(profile)'),
        (r"with open\('\.context_profile\.json', 'r'\) as f:",
         'with open(get_global_profile_path(__file__, ".context_profile.json"), "r") as f:'),
        (r"with open\('\.context_profile\.json', 'w'\) as f:",
         'with open(get_global_profile_path(__file__, ".context_profile.json"), "w") as f:'),
        # Log
        (r"fh = logging\.FileHandler\('context\.log'",
         'fh = logging.FileHandler(str(get_log_path(__file__)))'),
        # Archivo de estadísticas
        (r"with open\('context_stats\.json', 'w'",
         'with open(str(get_instance_dir(__file__) / "context_stats.json"), "w"'),
    ],
    "list_packages.py": [
        (r"fh = logging\.FileHandler\('pkg_list\.log'",
         'fh = logging.FileHandler(str(get_log_path(__file__, "pkg_list.log")))'),
        (r"load_profile\(profile_path=\"\.pkg_profile\.json\"\)",
         'load_profile(profile_path=str(get_global_profile_path(__file__, ".pkg_profile.json")))'),
        (r"save_profile\(profile, profile_path=\"\.pkg_profile\.json\"\)",
         'save_profile(profile, profile_path=str(get_global_profile_path(__file__, ".pkg_profile.json")))'),
        # También el perfil por defecto en la función load_profile
        (r"def load_profile\(profile_path=\"\.pkg_profile\.json\"\):",
         'def load_profile(profile_path=None):\n    if profile_path is None:\n        profile_path = str(get_global_profile_path(__file__, ".pkg_profile.json"))'),
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
        (r"load_profile\(filename\)",
         'load_profile(filename)'),
        (r"if not os\.path\.isfile\(filename\):",
         'if not os.path.isfile(filename):'),
        (r"with open\(filename, 'r'",
         'with open(filename, "r"'),
    ],
    "compress_to_path.py": [
        (r"PROFILE_FILE\s*=\s*['\"]\.compress_profile\.json['\"]",
         'PROFILE_FILE = str(get_global_profile_path(__file__, ".compress_profile.json"))'),
        (r"log_file = input\(.*compresor\.log.*\)",
         # Esto es más complejo, mejor reemplazar la asignación de log_file por defecto
         r'log_file = input\(colored\("Nombre del archivo de log \[compresor\.log\]: ", Colors.CYAN\)\).strip\(\) or "compresor.log"',
         'log_file = input(colored("Nombre del archivo de log [compresor.log]: ", Colors.CYAN)).strip() or str(get_log_path(__file__, "compresor.log"))'),
        # También en setup_logging
        (r"setup_logging\(quiet, log_file\)",
         'setup_logging(quiet, log_file)'),
    ],
    "http_server.py": [
        # Añadir import y redirigir log_message a un archivo
        # Se añadirá código al final del archivo o se modificará la clase.
        # Por simplicidad, añadimos una importación y modificamos el método log_message.
        (r"class CustomHandler\(BaseHTTPRequestHandler\):",
         'class CustomHandler(BaseHTTPRequestHandler):\n    def __init__(self, *args, **kwargs):\n        self.log_path = get_instance_dir(__file__) / "http_server.log"\n        super().__init__(*args, **kwargs)'),
        (r"def log_message\(self, format, \*args\):",
         '    def log_message(self, format, *args):\n        try:\n            with open(self.log_path, "a", encoding="utf-8") as f:\n                f.write(f"[{self.log_date_time_string()}] {args[0]}\\n")\n        except:\n            pass\n        sys.stderr.write(f"[{self.log_date_time_string()}] {args[0]}\\n")'),
    ],
    "start.py": [
        (r"LOG_FILE\s*=\s*REPO_DIR / \"start\.log\"",
         'LOG_FILE = get_log_path(__file__, "start.log")'),
        (r"logging\.basicConfig\(",
         'logging.basicConfig('),
    ],
    "bootstrap.py": [
        # No necesita cambios porque no guarda logs permanentes? Pero podemos añadir perfil?
        # Por ahora no.
    ],
}

# ─── Funciones auxiliares ──────────────────────────────────────────────────
def backup_file(filepath: Path) -> Path:
    """Crea una copia de seguridad del archivo."""
    backup = filepath.with_suffix(filepath.suffix + BACKUP_SUFFIX)
    shutil.copy2(filepath, backup)
    return backup

def add_import_if_missing(content: str, import_line: str) -> str:
    """Añade la línea de importación después de los imports existentes."""
    if import_line in content:
        return content
    # Buscar la última línea de importación
    lines = content.splitlines()
    insert_pos = 0
    for i, line in enumerate(lines):
        if line.startswith("import ") or line.startswith("from "):
            insert_pos = i + 1
        elif line.strip() and not line.startswith("#") and insert_pos > 0:
            break
    lines.insert(insert_pos, import_line)
    return "\n".join(lines)

def apply_replacements(filepath: Path, replacements: List[Tuple[str, str]]):
    """Aplica una serie de reemplazos al contenido del archivo."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    original = content
    for pattern, repl in replacements:
        # Si el patrón es regex, usar re.sub; si no, reemplazo simple
        if isinstance(pattern, re.Pattern):
            content = pattern.sub(repl, content)
        else:
            content = content.replace(pattern, repl)
    if content != original:
        # Hacer backup
        backup_file(filepath)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    return False

def migrate_script(script_path: Path) -> bool:
    """Migra un script individual."""
    print(f"Procesando {script_path.name}...")
    if script_path.name not in REPLACEMENTS:
        print(f"  No hay reemplazos definidos para {script_path.name}, omitiendo.")
        return False
    replacements = REPLACEMENTS[script_path.name]
    # Añadir importación de path_manager
    import_line = "from path_manager import get_repo_dir, get_script_dir, get_instance_dir, get_global_profile_path, get_log_path, get_cache_dir"
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()
    if "from path_manager import" not in content:
        content = add_import_if_missing(content, import_line)
        # Guardar después de añadir import
        backup_file(script_path)
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  Añadida importación en {script_path.name}")
    else:
        print(f"  La importación ya existe en {script_path.name}")
    # Aplicar reemplazos
    modified = apply_replacements(script_path, replacements)
    if modified:
        print(f"  Reemplazos aplicados en {script_path.name}")
    else:
        print(f"  No se realizaron cambios en {script_path.name}")
    return modified

def create_path_manager():
    """Crea path_manager.py si no existe."""
    path_manager = REPO_DIR / "path_manager.py"
    if not path_manager.exists():
        with open(path_manager, "w", encoding="utf-8") as f:
            f.write(PATH_MANAGER_CONTENT)
        print(f"Creado {path_manager}")
    else:
        print(f"✓ {path_manager} ya existe")

# ─── Main ──────────────────────────────────────────────────────────────────
def main():
    print("=== Herramienta de migración a path_manager ===\n")
    create_path_manager()
    print("\nBuscando scripts para migrar...")
    scripts = [p for p in REPO_DIR.glob("*.py") if p.name not in EXCLUDE_FILES]
    if not scripts:
        print("No se encontraron scripts para migrar.")
        return
    modified_count = 0
    for script in scripts:
        if migrate_script(script):
            modified_count += 1
    print(f"\n✅ Migración completada. {modified_count} archivo(s) modificado(s).")
    print("Se han creado copias de seguridad con extensión .bak. Revise los cambios antes de eliminar los backups.")
    print("\nNota: Algunos scripts pueden requerir ajustes manuales adicionales (por ejemplo, http_server.py).")

if __name__ == "__main__":
    main()