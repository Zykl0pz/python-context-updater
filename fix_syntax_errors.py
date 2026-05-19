#!/usr/bin/env python3
"""
fix_syntax_errors.py - Corrige errores de sintaxis generados por fix_migrations.py.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent

def fix_context_list_packages():
    """Corrige la línea de logging.FileHandler en context.py y list_packages.py."""
    scripts = ["context.py", "list_packages.py"]
    for script in scripts:
        path = REPO_ROOT / script
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # Buscar el patrón incorrecto: FileHandler(str(...))), encoding=
        # Debe ser FileHandler(str(...), encoding=...)
        # El patrón: fh = logging.FileHandler(str(get_log_path(...))), encoding='utf-8')
        # Cambiar a: fh = logging.FileHandler(str(get_log_path(...)), encoding='utf-8')
        pattern = r'(fh = logging\.FileHandler\(str\(get_log_path\([^)]+\)\))\), encoding='
        replacement = r'\1, encoding='
        new_content = re.sub(pattern, replacement, content)
        if new_content != content:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"✅ Corregido {script}")

def fix_http_server():
    """Arregla la indentación y posible error en http_server.py."""
    path = REPO_ROOT / "http_server.py"
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    # Buscar la línea 'class CustomHandler(BaseHTTPRequestHandler):'
    class_index = None
    for i, line in enumerate(lines):
        if line.strip().startswith("class CustomHandler"):
            class_index = i
            break
    if class_index is None:
        print("No se encontró la clase CustomHandler en http_server.py")
        return
    
    # Buscar la línea 'def __init__' insertada
    init_index = None
    for i in range(class_index+1, len(lines)):
        if lines[i].strip().startswith("def __init__"):
            init_index = i
            break
    if init_index is None:
        print("No se encontró __init__ en http_server.py")
        return
    
    # Verificar indentación: el __init__ debe estar indentado con 4 espacios
    # La línea original de clase está sin indentar. El método __init__ debe tener 4 espacios.
    # Además, después de super().__init__ debe haber una línea en blanco o el siguiente método.
    # Asegurar que el bloque __init__ está correcto.
    fixed = False
    # A veces se insertó mal y la línea 'def do_GET' quedó al mismo nivel que el __init__? No, pero puede faltar indentación.
    # También la línea que contiene 'self.log_path =' debe tener 8 espacios.
    # Revisamos el contenido actual.
    content = "".join(lines)
    # Buscar el patrón donde después de super().__init__ viene directamente 'def do_GET'
    # Debe haber un salto de línea y luego la definición del método.
    # Si no hay línea en blanco, no pasa nada, pero la indentación puede estar bien.
    # El error mencionaba línea 793: 'def do_GET(self):' con IndentationError, lo que sugiere que esa línea está indentada incorrectamente (quizás con espacios de más o de menos).
    # Verificamos la indentación de la línea 'def do_GET'
    for i, line in enumerate(lines):
        if line.strip().startswith("def do_GET"):
            # La indentación debería ser 4 espacios (un nivel)
            expected_indent = "    "
            if not line.startswith(expected_indent):
                # Reemplazar la indentación actual por 4 espacios
                stripped = line.lstrip()
                lines[i] = expected_indent + stripped
                fixed = True
            break
    # También corregir posible falta de indentación en otros métodos
    method_names = ["def do_GET", "def serve_directory_zip", "def serve_directory_listing", "def serve_file"]
    for i, line in enumerate(lines):
        for method in method_names:
            if line.strip().startswith(method):
                if not line.startswith("    "):
                    stripped = line.lstrip()
                    lines[i] = "    " + stripped
                    fixed = True
                break
    
    if fixed:
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print("✅ Corregida indentación en http_server.py")
    else:
        print("No se detectaron problemas de indentación en http_server.py (quizás ya estaba bien)")

def fix_extra_parentheses():
    """Corrige otros posibles paréntesis extra en otros scripts."""
    # Por ejemplo, en sort.py, rename.py, etc. Podría haber problemas similares.
    scripts = ["rename.py", "sort.py", "compress_to_path.py", "start.py"]
    for script in scripts:
        path = REPO_ROOT / script
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # Buscar cualquier patrón donde haya )) , encoding=  y reemplazar por ), encoding=
        # Patrón más general: )), encoding=
        new_content = re.sub(r'\)\),\s*encoding=', '), encoding=', content)
        if new_content != content:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"✅ Corregido paréntesis en {script}")

def main():
    print("=== Corrigiendo errores de sintaxis post-migración ===\n")
    fix_context_list_packages()
    fix_http_server()
    fix_extra_parentheses()
    print("\n✅ Corrección completada. Intenta ejecutar los scripts nuevamente.")

if __name__ == "__main__":
    main()