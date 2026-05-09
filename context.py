import os
import zipfile
import xml.etree.ElementTree as ET
import csv
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# Intentar importar charset-normalizer para detección de encoding
try:
    from charset_normalizer import from_bytes
    HAS_CHARSET_NORMALIZER = True
except ImportError:
    HAS_CHARSET_NORMALIZER = False
    print("⚠️  charset-normalizer no instalado, usando fallback de encodings.")

# Intentar importar pathspec para .gitignore
try:
    import pathspec
    HAS_PATHSPEC = True
except ImportError:
    HAS_PATHSPEC = False
    print("⚠️  pathspec no instalado, no se aplicarán reglas .gitignore.")

# Configuración de logging
logger = logging.getLogger('context_generator')
logger.setLevel(logging.DEBUG)

# Handler para archivo (todos los niveles)
fh = logging.FileHandler('context.log', encoding='utf-8')
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Handler para consola (solo INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(logging.Formatter('%(message)s'))

logger.addHandler(fh)
logger.addHandler(ch)

# Mapa de extensiones a lenguajes de programación
language_map = {
    '.py': 'Python',
    '.php': 'PHP',
    '.properties': 'Properties',
    '.gradle': 'Groovy',
    '.htaccess': 'HTACCESS',
    '.bat': 'Windows Bash',
    '.ps1': 'PowerShell',
    '.sh': 'Bash Scripting',
    '.env': 'ENV',
    '.lock': 'LOCK',
    '.json': 'JSON',
    '.feature': 'Feature',
    '.prisma': 'Prisma',
    '.db': 'Database',
    '.js': 'JavaScript',
    '.jsx': 'ReactJS',
    '.tsx': 'ReactTS',
    '.java': 'Java',
    '.c': 'C',
    '.cpp': 'C++',
    '.html': 'HTML',
    '.css': 'CSS',
    '.rb': 'Ruby',
    '.kt': 'Kotlin',
    '.go': 'Go (Golang)',
    '.swift': 'Swift',
    '.rs': 'Rust',
    '.cs': 'C#',
    '.r': 'R',
    '.R': 'R',
    '.pl': 'Perl',
    '.dart': 'Dart',
    '.lua': 'Lua',
    '.scala': 'Scala',
    '.hs': 'Haskell',
    '.ex': 'Elixir',
    '.exs': 'Elixir',
    '.erl': 'Erlang',
    '.clj': 'Clojure',
    '.fs': 'F#',
    '.ml': 'OCaml',
    '.jl': 'Julia',
    '.ts': 'TypeScript',
    '.groovy': 'Groovy',
    '.vb': 'VB.NET',
    '.m': 'Objective-C',
    '.coffee': 'CoffeeScript',
    'Dockerfile': 'Dockerfile',
    'Makefile': 'Makefile',
    '.sql': 'SQL',
    '.sol': 'Solidity',
    '.bas': 'VBA',
    '.cls': 'VBA',
    '.frm': 'VBA',
    '.f': 'Fortran',
    '.for': 'Fortran',
    '.f90': 'Fortran',
    '.asm': 'Assembly',
    '.s': 'Assembly',
    '.tcl': 'Tcl',
    '.scm': 'Scheme',
    '.lisp': 'Lisp',
    '.lsp': 'Lisp',
    '.xslt': 'XSLT',
    '.yml': 'YAML',
    '.cob': 'COBOL',
    '.cbl': 'COBOL',
    '.adb': 'Ada',
    '.ads': 'Ada',
    '.nim': 'Nim',
    '.cr': 'Crystal',
    '.zig': 'Zig',
    '.v': 'V',
    '.re': 'ReasonML',
    '.res': 'ReScript',
    '.csv': 'CSV',
    '.docx': 'Word Document',
    '.xlsx': 'Excel Spreadsheet',
    '.pptx': 'PowerPoint Presentation',
    '.odt': 'OpenDocument Text',
    '.ods': 'OpenDocument Spreadsheet',
    '.odp': 'OpenDocument Presentation',
    '.ipynb': 'Jupyter Notebook',
    '.ini': 'INI Config',
    '.cfg': 'Config File',
    '.toml': 'TOML',
}

# Directorios que se ignoran completamente en el árbol y en el recorrido
IGNORED_DIRS = {
    '__pycache__', 'node_modules', 'dist', 'out', 'build',
    'venv', 'env', '.git', '.svn', '.hg', '.idea', '.vscode', 'vendor', 'samples', 'old'
}

def format_size(size_bytes):
    """Convierte bytes a una cadena legible"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def should_ignore_dir(dirname):
    """Determina si un directorio debe ser ignorado."""
    if dirname.startswith('.'):
        return True
    if dirname in IGNORED_DIRS:
        return True
    return False

def load_gitignore_spec(start_path):
    """Carga las reglas de .gitignore si existe"""
    if not HAS_PATHSPEC:
        return None
    gitignore_path = os.path.join(start_path, '.gitignore')
    if os.path.isfile(gitignore_path):
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                lines = f.read().splitlines()
            return pathspec.PathSpec.from_lines('gitwildmatch', lines)
        except Exception as e:
            logger.warning(f"No se pudo procesar .gitignore: {e}")
    return None

def is_ignored_by_gitignore(rel_path, spec):
    """Comprueba si una ruta coincide con el .gitignore"""
    if spec is None:
        return False
    # pathspec espera rutas relativas con separadores '/'
    return spec.match_file(rel_path.replace(os.sep, '/'))

def get_language(extension):
    return language_map.get(extension, 'Texto')

def detect_encoding(filepath):
    """Detecta el encoding de un archivo usando charset-normalizer o fallback"""
    if HAS_CHARSET_NORMALIZER:
        try:
            with open(filepath, 'rb') as f:
                raw_data = f.read()
            result = from_bytes(raw_data)
            if result.best():
                return result.best().encoding
        except Exception as e:
            logger.debug(f"Error en charset_normalizer: {e}")
    # Fallback: probar encodings comunes
    COMMON_ENCODINGS = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1', 'utf-16', 'cp437', 'ascii']
    for enc in COMMON_ENCODINGS:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                f.read(1024)
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    return 'utf-8'  # último recurso

def read_csv_content(filepath):
    try:
        content = []
        encoding = detect_encoding(filepath)
        with open(filepath, 'r', encoding=encoding, newline='') as csvfile:
            csv_reader = csv.reader(csvfile)
            for i, row in enumerate(csv_reader):
                content.append(f"Fila {i+1}: {', '.join(row)}")
        return '\n'.join(content)
    except Exception as e:
        return f"[Error leyendo archivo CSV: {str(e)}]"

def read_docx_content(filepath):
    try:
        with zipfile.ZipFile(filepath) as docx:
            if 'word/document.xml' not in docx.namelist():
                return "[Estructura DOCX no reconocida]"
            with docx.open('word/document.xml') as document_file:
                tree = ET.parse(document_file)
                root = tree.getroot()
                ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                paragraphs = []
                for paragraph in root.findall('.//w:p', ns):
                    texts = []
                    for text_elem in paragraph.findall('.//w:t', ns):
                        if text_elem.text:
                            texts.append(text_elem.text)
                    if texts:
                        paragraphs.append(''.join(texts))
                return '\n'.join(paragraphs)
    except Exception as e:
        return f"[Error leyendo archivo DOCX: {str(e)}]"

def read_xlsx_content(filepath):
    try:
        with zipfile.ZipFile(filepath) as xlsx:
            shared_strings = []
            if 'xl/sharedStrings.xml' in xlsx.namelist():
                with xlsx.open('xl/sharedStrings.xml') as shared_strings_file:
                    tree = ET.parse(shared_strings_file)
                    root = tree.getroot()
                    ns = {'': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                    for string_elem in root.findall('.//t', ns):
                        if string_elem.text:
                            shared_strings.append(string_elem.text)
            sheets_content = []
            sheet_files = [name for name in xlsx.namelist()
                          if name.startswith('xl/worksheets/sheet') and name.endswith('.xml')]
            for sheet_file in sheet_files:
                with xlsx.open(sheet_file) as sheet_file_obj:
                    tree = ET.parse(sheet_file_obj)
                    root = tree.getroot()
                    ns = {'': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                    sheet_data = []
                    for cell in root.findall('.//c', ns):
                        value_elem = cell.find('.//v', ns)
                        if value_elem is not None and value_elem.text:
                            if cell.get('t') == 's':
                                idx = int(value_elem.text)
                                if idx < len(shared_strings):
                                    sheet_data.append(shared_strings[idx])
                            else:
                                sheet_data.append(value_elem.text)
                    if sheet_data:
                        sheet_name = os.path.basename(sheet_file)
                        sheets_content.append(f"--- Hoja: {sheet_name} ---")
                        sheets_content.extend(sheet_data)
            return '\n'.join(sheets_content) if sheets_content else "[Archivo XLSX vacío o sin datos legibles]"
    except Exception as e:
        return f"[Error leyendo archivo XLSX: {str(e)}]"

def read_pptx_content(filepath):
    try:
        with zipfile.ZipFile(filepath) as pptx:
            slides_content = []
            slide_files = [name for name in pptx.namelist()
                          if name.startswith('ppt/slides/slide') and name.endswith('.xml')]
            for slide_file in slide_files:
                with pptx.open(slide_file) as slide_file_obj:
                    tree = ET.parse(slide_file_obj)
                    root = tree.getroot()
                    ns = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
                    slide_texts = []
                    for text_elem in root.findall('.//a:t', ns):
                        if text_elem.text:
                            slide_texts.append(text_elem.text)
                    if slide_texts:
                        slide_name = os.path.basename(slide_file)
                        slides_content.append(f"--- Diapositiva: {slide_name} ---")
                        slides_content.extend(slide_texts)
            return '\n'.join(slides_content) if slides_content else "[Archivo PPTX vacío o sin texto legible]"
    except Exception as e:
        return f"[Error leyendo archivo PPTX: {str(e)}]"

def read_odt_content(filepath):
    """OpenDocument Text (.odt)"""
    try:
        with zipfile.ZipFile(filepath) as odt:
            if 'content.xml' not in odt.namelist():
                return "[Estructura ODT no reconocida]"
            with odt.open('content.xml') as content_file:
                tree = ET.parse(content_file)
                root = tree.getroot()
                ns = {'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0'}
                paragraphs = []
                for p in root.findall('.//text:p', ns):
                    texts = []
                    for elem in p.iter():
                        if elem.text:
                            texts.append(elem.text)
                    if texts:
                        paragraphs.append(''.join(texts))
                return '\n'.join(paragraphs)
    except Exception as e:
        return f"[Error leyendo archivo ODT: {str(e)}]"

def read_ods_content(filepath):
    """OpenDocument Spreadsheet (.ods)"""
    try:
        with zipfile.ZipFile(filepath) as ods:
            if 'content.xml' not in ods.namelist():
                return "[Estructura ODS no reconocida]"
            with ods.open('content.xml') as content_file:
                tree = ET.parse(content_file)
                root = tree.getroot()
                ns = {
                    'table': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0',
                    'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0'
                }
                sheets = []
                for table in root.findall('.//table:table', ns):
                    table_name = table.get('{urn:oasis:names:tc:opendocument:xmlns:table:1.0}name')
                    rows = []
                    for row in table.findall('.//table:table-row', ns):
                        cells_text = []
                        for cell in row.findall('.//table:table-cell', ns):
                            texts = [t.text or '' for t in cell.findall('.//text:p', ns)]
                            cells_text.append(' '.join(texts))
                        rows.append(' | '.join(cells_text))
                    if rows:
                        sheets.append(f"--- Hoja: {table_name} ---")
                        sheets.extend(rows)
                return '\n'.join(sheets) if sheets else "[Archivo ODS vacío]"
    except Exception as e:
        return f"[Error leyendo archivo ODS: {str(e)}]"

def read_odp_content(filepath):
    """OpenDocument Presentation (.odp)"""
    try:
        with zipfile.ZipFile(filepath) as odp:
            if 'content.xml' not in odp.namelist():
                return "[Estructura ODP no reconocida]"
            with odp.open('content.xml') as content_file:
                tree = ET.parse(content_file)
                root = tree.getroot()
                ns = {
                    'draw': 'urn:oasis:names:tc:opendocument:xmlns:drawing:1.0',
                    'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
                    'svg': 'urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0'
                }
                slides = []
                for page in root.findall('.//draw:page', ns):
                    page_name = page.get('{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}name')
                    texts = []
                    for elem in page.findall('.//text:p', ns):
                        if elem.text:
                            texts.append(elem.text)
                    if texts:
                        slides.append(f"--- Diapositiva: {page_name} ---")
                        slides.extend(texts)
                return '\n'.join(slides) if slides else "[Archivo ODP vacío]"
    except Exception as e:
        return f"[Error leyendo archivo ODP: {str(e)}]"

def read_ipynb_content(filepath):
    """Jupyter Notebook (.ipynb)"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            nb = json.load(f)
        cells = nb.get('cells', [])
        output = []
        for idx, cell in enumerate(cells, 1):
            cell_type = cell.get('cell_type', '')
            source = ''.join(cell.get('source', []))
            if cell_type == 'code':
                output.append(f"[Código celda {idx}]\n{source}")
            elif cell_type == 'markdown':
                output.append(f"[Markdown celda {idx}]\n{source}")
            else:
                output.append(f"[{cell_type} celda {idx}]\n{source}")
        return '\n'.join(output) if output else "[Archivo IPYNB vacío]"
    except Exception as e:
        return f"[Error leyendo archivo IPYNB: {str(e)}]"

def read_file_content(filepath):
    """Lee el contenido de un archivo, manejando formatos especiales o texto plano"""
    _, ext = os.path.splitext(filepath)
    ext = ext.lower()

    # Formatos especiales
    if ext == '.csv':
        return read_csv_content(filepath)
    elif ext == '.docx':
        return read_docx_content(filepath)
    elif ext == '.xlsx':
        return read_xlsx_content(filepath)
    elif ext == '.pptx':
        return read_pptx_content(filepath)
    elif ext == '.odt':
        return read_odt_content(filepath)
    elif ext == '.ods':
        return read_ods_content(filepath)
    elif ext == '.odp':
        return read_odp_content(filepath)
    elif ext == '.ipynb':
        return read_ipynb_content(filepath)
    else:
        # Archivos de texto, detectar si es binario
        try:
            with open(filepath, 'rb') as f:
                raw_head = f.read(1024)
            if b'\x00' in raw_head:
                return "[Archivo binario - omitido]"
        except Exception:
            return "[Error accediendo al archivo]"

        # Detectar encoding
        encoding = detect_encoding(filepath)
        try:
            with open(filepath, 'r', encoding=encoding, errors='replace') as f:
                content = f.read()
            # Comprobar caracteres de control excesivos
            control_chars = sum(1 for c in content if ord(c) < 32 and c not in '\n\r\t')
            if len(content) > 0 and control_chars / len(content) > 0.1:
                return "[Posible archivo binario - omitido]"
            return content
        except Exception as e:
            return f"[No se pudo leer el archivo: {str(e)}]"

def get_available_extensions():
    """Obtiene todas las extensiones disponibles en el directorio actual que están en language_map"""
    extensions = set()
    for root, dirs, files in os.walk('.', followlinks=False):
        dirs[:] = [d for d in dirs if not should_ignore_dir(d)]
        for filename in files:
            filepath = os.path.join(root, filename)
            if os.path.isfile(filepath) and not os.path.islink(filepath):
                _, ext = os.path.splitext(filename)
                if ext and ext.lower() in language_map:
                    extensions.add(ext.lower())
    return sorted(extensions)

def select_extensions_interactively():
    """Permite al usuario seleccionar extensiones de forma interactiva"""
    available_extensions = get_available_extensions()
    if not available_extensions:
        print("No se encontraron archivos con extensiones reconocidas en el directorio actual.")
        print("Extensiones reconocidas:", ", ".join(sorted(language_map.keys())))
        return []
    print("\nExtensiones disponibles en el directorio (solo las reconocidas):")
    print("=" * 60)
    for i, ext in enumerate(available_extensions, 1):
        language = get_language(ext)
        print(f"{i:2d}. {ext:10} -> {language}")
    print("\nOpciones:")
    print("  - Ingresa los números de las extensiones separados por comas (ej: 1,3,5)")
    print("  - 'all' para seleccionar todas las extensiones")
    print("  - 'none' para no seleccionar ninguna")
    print("  - 'common' para seleccionar extensiones comunes de código")
    print("  - 'office' para seleccionar extensiones de Office (docx, xlsx, pptx, csv, odt, ods, odp)")
    while True:
        selection = input("\nTu selección: ").strip().lower()
        if selection == 'all':
            return available_extensions
        elif selection == 'none':
            return []
        elif selection == 'common':
            common_exts = {'.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.c', '.cpp', '.html',
                          '.css', '.rb', '.php', '.go', '.rs', '.cs', '.swift', '.kt', '.dart'}
            return [ext for ext in available_extensions if ext in common_exts]
        elif selection == 'office':
            office_exts = {'.csv', '.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp', '.pdf'}
            return [ext for ext in available_extensions if ext in office_exts]
        elif selection:
            try:
                selected_indices = [int(x.strip()) for x in selection.split(',')]
                selected_extensions = []
                for idx in selected_indices:
                    if 1 <= idx <= len(available_extensions):
                        selected_extensions.append(available_extensions[idx-1])
                    else:
                        print(f"Advertencia: El número {idx} está fuera de rango")
                if selected_extensions:
                    return selected_extensions
                else:
                    print("No seleccionaste ninguna extensión válida. Intenta nuevamente.")
            except ValueError:
                print("Por favor, ingresa números válidos separados por comas.")
        else:
            print("Por favor, ingresa una selección válida.")

def generate_directory_tree(start_path='.'):
    """
    Genera una representación en árbol con tamaño de archivo,
    ignorando los directorios y archivos según .gitignore.
    """
    git_spec = load_gitignore_spec(start_path)
    lines = []
    lines.append(start_path)

    def walk_dir(current_path, prefix=""):
        try:
            items = os.listdir(current_path)
        except PermissionError:
            lines.append(prefix + "└── [Permiso denegado]")
            return
        dirs = []
        files = []
        for item in items:
            full_path = os.path.join(current_path, item)
            rel_path = os.path.relpath(full_path, start_path)
            # Ignorar por regla .gitignore
            if is_ignored_by_gitignore(rel_path, git_spec):
                continue
            if os.path.isdir(full_path):
                if not should_ignore_dir(item):
                    dirs.append(item)
            else:
                # No ignorar archivos aquí, solo directorios se filtran en os.walk
                files.append(item)

        dirs.sort()
        files.sort()

        # Procesar directorios
        for i, d in enumerate(dirs):
            is_last_dir = (i == len(dirs) - 1) and (len(files) == 0)
            connector = "└── " if is_last_dir else "├── "
            lines.append(prefix + connector + d + "/")
            new_prefix = prefix + "    " if is_last_dir else prefix + "│   "
            walk_dir(os.path.join(current_path, d), new_prefix)

        # Procesar archivos con tamaño
        for i, f in enumerate(files):
            is_last_file = (i == len(files) - 1)
            connector = "└── " if is_last_file else "├── "
            full_path = os.path.join(current_path, f)
            try:
                size = os.path.getsize(full_path)
                size_str = format_size(size)
            except OSError:
                size_str = "???"
            lines.append(f"{prefix}{connector}{f} ({size_str})")

    walk_dir(start_path)
    return '\n'.join(lines)

def select_output_format():
    """Pregunta al usuario por el formato de salida"""
    print("\nFormato de salida:")
    print("1. Markdown (.md)")
    print("2. JSON (.json)")
    print("3. XML (.xml)")
    print("4. Texto plano (.txt)")
    while True:
        choice = input("Elige una opción (1-4) [1]: ").strip()
        if choice == '' or choice == '1':
            return 'md'
        elif choice == '2':
            return 'json'
        elif choice == '3':
            return 'xml'
        elif choice == '4':
            return 'txt'
        else:
            print("Opción no válida, intenta de nuevo.")

def write_output_md(selected_extensions, tree_text, file_data):
    """Escribe el contexto en formato Markdown mejorado"""
    output_file = 'context.md'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# CONTEXTO DEL PROYECTO\n\n")
        f.write(f"**Extensiones incluidas:** {', '.join(selected_extensions)}\n\n")
        f.write("## ESTRUCTURA DE DIRECTORIOS\n\n")
        f.write("```\n")
        f.write(tree_text)
        f.write("\n```\n\n")
        f.write("---\n\n")
        f.write("## CONTENIDO DE ARCHIVOS SELECCIONADOS\n\n")
        for file in file_data:
            f.write(f"### ./{file['relative_path']}\n")
            language = file['language'].replace(' ', '-') if file['language'] else ''
            f.write(f"```{language}\n")
            # Si está vacío, marcarlo explícitamente
            content = file['content']
            if not content.strip():
                f.write("[Archivo vacío]\n")
            else:
                f.write(content)
            f.write("\n```\n\n---\n\n")
    return output_file

def write_output_json(selected_extensions, tree_text, file_data):
    """Escribe en JSON"""
    output_file = 'context.json'
    data = {
        'extensions': selected_extensions,
        'directory_tree': tree_text,
        'files': [
            {
                'path': d['relative_path'],
                'language': d['language'],
                'content': d['content']
            } for d in file_data
        ]
    }
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return output_file

def write_output_xml(selected_extensions, tree_text, file_data):
    """Escribe en XML básico"""
    output_file = 'context.xml'
    root = ET.Element('context')
    ET.SubElement(root, 'extensions').text = ', '.join(selected_extensions)
    tree_elem = ET.SubElement(root, 'directory_tree')
    tree_elem.text = tree_text
    files_elem = ET.SubElement(root, 'files')
    for d in file_data:
        file_elem = ET.SubElement(files_elem, 'file')
        ET.SubElement(file_elem, 'path').text = d['relative_path']
        ET.SubElement(file_elem, 'language').text = d['language']
        content_elem = ET.SubElement(file_elem, 'content')
        content_elem.text = d['content']
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(output_file, encoding='utf-8', xml_declaration=True)
    return output_file

def write_output_txt(selected_extensions, tree_text, file_data):
    """Escribe en texto plano"""
    output_file = 'context.txt'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("CONTEXTO DEL PROYECTO\n")
        f.write(f"Extensiones: {', '.join(selected_extensions)}\n\n")
        f.write("ESTRUCTURA DE DIRECTORIOS\n")
        f.write(tree_text)
        f.write("\n\n" + "="*50 + "\n\n")
        for d in file_data:
            f.write(f"./{d['relative_path']}\n")
            f.write(f"Lenguaje: {d['language']}\n")
            f.write(d['content'] if d['content'].strip() else "[Archivo vacío]\n")
            f.write("\n" + "="*50 + "\n\n")
    return output_file

def main():
    logger.info("Generador de Contexto de Código")
    logger.info("=" * 40)

    # Selección interactiva de extensiones
    selected_extensions = select_extensions_interactively()
    if not selected_extensions:
        logger.info("No se seleccionaron extensiones. Saliendo...")
        return

    # Seleccionar formato de salida
    output_format = select_output_format()
    logger.info(f"Extensiones seleccionadas: {', '.join(selected_extensions)}")
    logger.info(f"Formato de salida: {output_format}")

    # Generar árbol de directorios con tamaños
    logger.info("Generando árbol de directorios...")
    tree_text = generate_directory_tree()
    logger.info("Árbol generado.")

    # Cargar .gitignore spec para el recorrido de archivos
    git_spec = load_gitignore_spec('.')
    logger.info("Buscando archivos...")

    # Recopilar archivos a procesar
    file_list = []
    for root, dirs, files in os.walk('.', followlinks=False):
        # Filtrar directorios
        dirs[:] = [d for d in dirs if not should_ignore_dir(d) and not is_ignored_by_gitignore(os.path.relpath(os.path.join(root, d), '.'), git_spec)]
        for filename in files:
            filepath = os.path.join(root, filename)
            # Ignorar enlaces simbólicos y archivos que no pasen .gitignore
            if os.path.islink(filepath):
                continue
            rel_path = os.path.relpath(filepath, '.')
            if is_ignored_by_gitignore(rel_path, git_spec):
                continue
            _, ext = os.path.splitext(filename)
            if ext.lower() in selected_extensions and ext.lower() in language_map:
                language = get_language(ext)
                file_list.append((filepath, rel_path, language))

    total_files = len(file_list)
    logger.info(f"Se procesarán {total_files} archivos.")
    logger.info("Leyendo contenidos (en paralelo)...")

    # Procesamiento concurrente
    file_data = []
    # Mantener orden original
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_index = {}
        for idx, (filepath, rel_path, lang) in enumerate(file_list):
            future = executor.submit(read_file_content, filepath)
            future_to_index[future] = idx
        results = [None] * total_files
        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            content = future.result()
            results[idx] = content
        # Construir lista ordenada
        for i, (filepath, rel_path, lang) in enumerate(file_list):
            content = results[i] if results[i] is not None else "[Error desconocido]"
            file_data.append({
                'relative_path': rel_path,
                'language': lang,
                'content': content
            })

    # Escribir salida según formato
    if output_format == 'md':
        out_file = write_output_md(selected_extensions, tree_text, file_data)
    elif output_format == 'json':
        out_file = write_output_json(selected_extensions, tree_text, file_data)
    elif output_format == 'xml':
        out_file = write_output_xml(selected_extensions, tree_text, file_data)
    elif output_format == 'txt':
        out_file = write_output_txt(selected_extensions, tree_text, file_data)

    # Estadísticas finales
    total_lines = sum(d['content'].count('\n') for d in file_data)
    total_size = sum(os.path.getsize(os.path.join('.', d['relative_path'])) for d in file_data if os.path.isfile(os.path.join('.', d['relative_path'])))
    lang_counts = {}
    for d in file_data:
        lang = d['language']
        lang_counts[lang] = lang_counts.get(lang, 0) + 1

    logger.info("\n" + "="*50)
    logger.info("RESUMEN FINAL")
    logger.info(f"Archivos procesados: {total_files}")
    logger.info(f"Líneas totales (aproximado): {total_lines}")
    logger.info(f"Tamaño total: {format_size(total_size)}")
    logger.info("Archivos por lenguaje:")
    for lang, count in sorted(lang_counts.items(), key=lambda x: x[1], reverse=True):
        logger.info(f"  {lang}: {count}")
    logger.info(f"Archivo de salida: {out_file}")
    logger.info("Proceso completado.")

if __name__ == '__main__':
    main()