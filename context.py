import os
import zipfile
import xml.etree.ElementTree as ET
import csv
import json
import fnmatch
import logging
import platform
import sys
import getpass
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from path_manager import get_repo_dir, get_script_dir, get_instance_dir, get_global_profile_path, get_log_path, get_cache_dir

# ─── Dependencias opcionales ───────────────────────────────────────────────
try:
    from charset_normalizer import from_bytes
    HAS_CHARSET_NORMALIZER = True
except ImportError:
    HAS_CHARSET_NORMALIZER = False

try:
    import pathspec
    HAS_PATHSPEC = True
except ImportError:
    HAS_PATHSPEC = False

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

# ─── Colores ANSI para terminal ────────────────────────────────────────────
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def colored(text, color):
    if sys.stdout.isatty():
        return f"{color}{text}{Colors.ENDC}"
    return text

# ─── Configuración de logging ──────────────────────────────────────────────
logger = logging.getLogger('context_generator')
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('context.log', encoding='utf-8')
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(fh)
logger.addHandler(ch)

# ─── Mapa de extensiones a lenguajes ───────────────────────────────────────
language_map = {
    '.py': 'Python','.md': 'Markdown', '.php': 'PHP', '.properties': 'Properties', '.gradle': 'Groovy',
    '.htaccess': 'HTACCESS', '.bat': 'Windows Bash', '.ps1': 'PowerShell', '.sh': 'Bash Scripting',
    '.env': 'ENV', '.lock': 'LOCK', '.json': 'JSON', '.feature': 'Feature', '.prisma': 'Prisma',
    '.db': 'Database', '.js': 'JavaScript', '.jsx': 'ReactJS', '.tsx': 'ReactTS',
    '.java': 'Java', '.c': 'C', '.cpp': 'C++', '.html': 'HTML', '.css': 'CSS', '.rb': 'Ruby',
    '.kt': 'Kotlin', '.go': 'Go (Golang)', '.swift': 'Swift', '.rs': 'Rust', '.cs': 'C#', '.r': 'R',
    '.R': 'R', '.pl': 'Perl', '.dart': 'Dart', '.lua': 'Lua', '.scala': 'Scala', '.hs': 'Haskell',
    '.ex': 'Elixir', '.exs': 'Elixir', '.erl': 'Erlang', '.clj': 'Clojure', '.fs': 'F#', '.ml': 'OCaml',
    '.jl': 'Julia', '.ts': 'TypeScript', '.groovy': 'Groovy', '.vb': 'VB.NET', '.m': 'Objective-C',
    '.coffee': 'CoffeeScript', 'Dockerfile': 'Dockerfile', 'Makefile': 'Makefile', '.sql': 'SQL',
    '.sol': 'Solidity', '.bas': 'VBA', '.cls': 'VBA', '.frm': 'VBA', '.f': 'Fortran', '.for': 'Fortran',
    '.f90': 'Fortran', '.asm': 'Assembly', '.s': 'Assembly', '.tcl': 'Tcl', '.scm': 'Scheme',
    '.lisp': 'Lisp', '.lsp': 'Lisp', '.xslt': 'XSLT', '.yml': 'YAML', '.yaml': 'YAML', '.cob': 'COBOL',
    '.cbl': 'COBOL', '.adb': 'Ada', '.ads': 'Ada', '.nim': 'Nim', '.cr': 'Crystal', '.zig': 'Zig',
    '.v': 'V', '.re': 'ReasonML', '.res': 'ReScript', '.csv': 'CSV', '.docx': 'Word Document',
    '.xlsx': 'Excel Spreadsheet', '.pptx': 'PowerPoint Presentation', '.odt': 'OpenDocument Text',
    '.ods': 'OpenDocument Spreadsheet', '.odp': 'OpenDocument Presentation', '.ipynb': 'Jupyter Notebook',
    '.ini': 'INI Config', '.cfg': 'Config File', '.toml': 'TOML', '.pdf': 'PDF Document',
}

# ─── Directorios ignorados por defecto ─────────────────────────────────────
DEFAULT_IGNORED_DIRS = {
    '__pycache__', 'node_modules', 'dist', 'out', 'build',
    'venv', 'env', '.git', '.svn', '.hg', '.idea', '.vscode', 'vendor', 'samples', 'old'
}

# ─── Utilidades de formato y archivos ──────────────────────────────────────
def format_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def get_language(extension):
    return language_map.get(extension, 'Texto')

# ─── Encoding cache ────────────────────────────────────────────────────────
_encoding_cache = {}

def detect_encoding(filepath):
    """Detecta el encoding con caché."""
    path = str(filepath) if not isinstance(filepath, str) else filepath
    if path in _encoding_cache:
        return _encoding_cache[path]
    if HAS_CHARSET_NORMALIZER:
        try:
            with open(filepath, 'rb') as f:
                raw_data = f.read()
            result = from_bytes(raw_data)
            if result.best():
                enc = result.best().encoding
                _encoding_cache[path] = enc
                return enc
        except Exception:
            pass
    COMMON = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1', 'utf-16', 'cp437', 'ascii']
    for enc in COMMON:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                f.read(1024)
            _encoding_cache[path] = enc
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    enc = 'utf-8'
    _encoding_cache[path] = enc
    return enc

# ─── Gestión de .contextignore ────────────────────────────────────────────
CONTEXTIGNORE_FILE = '.contextignore'

def load_contextignore(start_path='.'):
    """Lee el .contextignore o lo crea con los directorios ignorados por defecto."""
    path = os.path.join(start_path, CONTEXTIGNORE_FILE)
    if not os.path.isfile(path):
        # Crear con las carpetas por defecto (cada una como patrón directorio)
        patterns = [f"{d}/" for d in sorted(DEFAULT_IGNORED_DIRS)]
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write("\n".join(patterns) + "\n")
            logger.info(f"Creado {CONTEXTIGNORE_FILE} con directorios ignorados por defecto.")
        except Exception as e:
            logger.warning(f"No se pudo crear {CONTEXTIGNORE_FILE}: {e}")
            return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        return lines
    except Exception as e:
        logger.warning(f"Error leyendo {CONTEXTIGNORE_FILE}: {e}")
        return []

def should_ignore_by_contextignore(rel_path, patterns):
    """Comprueba si la ruta relativa coincide con algún patrón de .contextignore."""
    if not patterns:
        return False
    # Normalizar a '/'
    path = rel_path.replace(os.sep, '/')
    for pat in patterns:
        # Si el patrón termina con '/', es un directorio
        if pat.endswith('/'):
            # Comprobar si la ruta es exactamente ese directorio o está dentro
            if path == pat.rstrip('/') or path.startswith(pat):
                return True
        else:
            if fnmatch.fnmatch(path, pat):
                return True
    return False

def should_ignore_dir_basic(dirname):
    return dirname.startswith('.')

# ─── Lectura de formatos especiales ────────────────────────────────────────
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
            with docx.open('word/document.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                paragraphs = []
                for p in root.findall('.//w:p', ns):
                    texts = [t.text for t in p.findall('.//w:t', ns) if t.text]
                    if texts:
                        paragraphs.append(''.join(texts))
                return '\n'.join(paragraphs)
    except Exception as e:
        return f"[Error leyendo DOCX: {str(e)}]"

def read_xlsx_content(filepath):
    try:
        with zipfile.ZipFile(filepath) as xlsx:
            shared_strings = []
            if 'xl/sharedStrings.xml' in xlsx.namelist():
                with xlsx.open('xl/sharedStrings.xml') as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    ns = {'': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                    for si in root.findall('.//t', ns):
                        if si.text:
                            shared_strings.append(si.text)
            sheets_content = []
            sheet_files = [n for n in xlsx.namelist() if n.startswith('xl/worksheets/sheet') and n.endswith('.xml')]
            for sheet_file in sheet_files:
                with xlsx.open(sheet_file) as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    ns = {'': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                    sheet_data = []
                    for cell in root.findall('.//c', ns):
                        v = cell.find('.//v', ns)
                        if v is not None and v.text:
                            if cell.get('t') == 's':
                                idx = int(v.text)
                                if idx < len(shared_strings):
                                    sheet_data.append(shared_strings[idx])
                            else:
                                sheet_data.append(v.text)
                    if sheet_data:
                        sheets_content.append(f"--- Hoja: {os.path.basename(sheet_file)} ---")
                        sheets_content.extend(sheet_data)
            return '\n'.join(sheets_content) if sheets_content else "[Archivo XLSX vacío o sin datos]"
    except Exception as e:
        return f"[Error leyendo XLSX: {str(e)}]"

def read_pptx_content(filepath):
    try:
        with zipfile.ZipFile(filepath) as pptx:
            slides_content = []
            slide_files = [n for n in pptx.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]
            for slide_file in slide_files:
                with pptx.open(slide_file) as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    ns = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
                    texts = [t.text for t in root.findall('.//a:t', ns) if t.text]
                    if texts:
                        slides_content.append(f"--- Diapositiva: {os.path.basename(slide_file)} ---")
                        slides_content.extend(texts)
            return '\n'.join(slides_content) if slides_content else "[Archivo PPTX vacío]"
    except Exception as e:
        return f"[Error leyendo PPTX: {str(e)}]"

def read_odt_content(filepath):
    try:
        with zipfile.ZipFile(filepath) as odt:
            if 'content.xml' not in odt.namelist():
                return "[Estructura ODT no reconocida]"
            with odt.open('content.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                ns = {'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0'}
                paragraphs = []
                for p in root.findall('.//text:p', ns):
                    text = ''.join(t.text or '' for t in p.iter() if t.text)
                    if text.strip():
                        paragraphs.append(text)
                return '\n'.join(paragraphs) if paragraphs else "[Archivo ODT vacío]"
    except Exception as e:
        return f"[Error leyendo ODT: {str(e)}]"

def read_ods_content(filepath):
    try:
        with zipfile.ZipFile(filepath) as ods:
            if 'content.xml' not in ods.namelist():
                return "[Estructura ODS no reconocida]"
            with ods.open('content.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                ns = {
                    'table': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0',
                    'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0'
                }
                sheets = []
                for table in root.findall('.//table:table', ns):
                    name = table.get('{urn:oasis:names:tc:opendocument:xmlns:table:1.0}name')
                    rows = []
                    for row in table.findall('.//table:table-row', ns):
                        cells = []
                        for cell in row.findall('.//table:table-cell', ns):
                            cell_text = ' '.join(t.text or '' for t in cell.findall('.//text:p', ns))
                            cells.append(cell_text)
                        rows.append(' | '.join(cells))
                    if rows:
                        sheets.append(f"--- Hoja: {name} ---")
                        sheets.extend(rows)
                return '\n'.join(sheets) if sheets else "[Archivo ODS vacío]"
    except Exception as e:
        return f"[Error leyendo ODS: {str(e)}]"

def read_odp_content(filepath):
    try:
        with zipfile.ZipFile(filepath) as odp:
            if 'content.xml' not in odp.namelist():
                return "[Estructura ODP no reconocida]"
            with odp.open('content.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                ns = {
                    'draw': 'urn:oasis:names:tc:opendocument:xmlns:drawing:1.0',
                    'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0'
                }
                slides = []
                for page in root.findall('.//draw:page', ns):
                    pname = page.get('{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}name')
                    texts = [t.text for t in page.findall('.//text:p', ns) if t.text]
                    if texts:
                        slides.append(f"--- Diapositiva: {pname} ---")
                        slides.extend(texts)
                return '\n'.join(slides) if slides else "[Archivo ODP vacío]"
    except Exception as e:
        return f"[Error leyendo ODP: {str(e)}]"

def read_ipynb_content(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            nb = json.load(f)
        cells = nb.get('cells', [])
        output = []
        for idx, cell in enumerate(cells, 1):
            cell_type = cell.get('cell_type', '')
            source = ''.join(cell.get('source', []))
            output.append(f"[{cell_type.capitalize()} celda {idx}]\n{source}")
        return '\n'.join(output) if output else "[Archivo IPYNB vacío]"
    except Exception as e:
        return f"[Error leyendo IPYNB: {str(e)}]"

def read_pdf_content(filepath):
    """Extrae texto de un PDF usando PyPDF2 o pdfplumber (si están disponibles)."""
    if HAS_PDFPLUMBER:
        try:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                pages_text = []
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    if text:
                        pages_text.append(f"--- Página {i+1} ---\n{text}")
                return '\n'.join(pages_text) if pages_text else "[PDF sin texto legible]"
        except Exception as e:
            return f"[Error con pdfplumber: {str(e)}]"
    if HAS_PYPDF2:
        try:
            with open(filepath, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                pages_text = []
                for i, page in enumerate(pdf_reader.pages):
                    text = page.extract_text()
                    if text:
                        pages_text.append(f"--- Página {i+1} ---\n{text}")
                return '\n'.join(pages_text) if pages_text else "[PDF sin texto legible]"
        except Exception as e:
            return f"[Error con PyPDF2: {str(e)}]"
    return "[PDF no procesado (instala PyPDF2 o pdfplumber)]"

def read_file_content(filepath):
    """Lee el contenido según la extensión."""
    _, ext = os.path.splitext(filepath)
    ext = ext.lower()

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
    elif ext == '.pdf':
        return read_pdf_content(filepath)
    else:
        # Archivo de texto genérico
        try:
            with open(filepath, 'rb') as f:
                if b'\x00' in f.read(1024):
                    return "[Archivo binario - omitido]"
        except Exception:
            return "[Error accediendo al archivo]"
        encoding = detect_encoding(filepath)
        try:
            with open(filepath, 'r', encoding=encoding, errors='replace') as f:
                content = f.read()
            # Heurística de binario
            if len(content) > 0:
                control = sum(1 for c in content if ord(c) < 32 and c not in '\n\r\t')
                if control / len(content) > 0.1:
                    return "[Posible archivo binario - omitido]"
            return content
        except Exception as e:
            return f"[No se pudo leer el archivo: {str(e)}]"

# ─── Árbol de directorios con .contextignore y .gitignore ─────────────────
def generate_directory_tree(start_path='.', context_patterns=None, git_spec=None):
    lines = []
    lines.append(start_path)

    def walk_dir(current_path, prefix=""):
        try:
            items = os.listdir(current_path)
        except PermissionError:
            lines.append(prefix + "└── [Permiso denegado]")
            return
        dirs, files = [], []
        for item in items:
            full = os.path.join(current_path, item)
            rel = os.path.relpath(full, start_path)
            # Aplicar .gitignore si existe
            if git_spec and is_ignored_by_gitignore(rel, git_spec):
                continue
            if os.path.isdir(full):
                if not should_ignore_dir_basic(item) and not should_ignore_by_contextignore(rel + '/', context_patterns):
                    dirs.append(item)
            else:
                files.append(item)
        dirs.sort()
        files.sort()
        for i, d in enumerate(dirs):
            last = (i == len(dirs)-1) and (len(files) == 0)
            conn = "└── " if last else "├── "
            lines.append(prefix + conn + d + "/")
            new_prefix = prefix + "    " if last else prefix + "│   "
            walk_dir(os.path.join(current_path, d), new_prefix)
        for i, f in enumerate(files):
            last = (i == len(files)-1)
            conn = "└── " if last else "├── "
            full = os.path.join(current_path, f)
            try:
                size = format_size(os.path.getsize(full))
            except OSError:
                size = "???"
            lines.append(f"{prefix}{conn}{f} ({size})")

    walk_dir(start_path)
    return '\n'.join(lines)

def is_ignored_by_gitignore(rel_path, spec):
    if spec is None:
        return False
    return spec.match_file(rel_path.replace(os.sep, '/'))

# ─── Interacción con el usuario ───────────────────────────────────────────
def get_available_extensions():
    extensions = set()
    for root, dirs, files in os.walk('.', followlinks=False):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for filename in files:
            filepath = os.path.join(root, filename)
            if os.path.isfile(filepath) and not os.path.islink(filepath):
                _, ext = os.path.splitext(filename)
                if ext and ext.lower() in language_map:
                    extensions.add(ext.lower())
    return sorted(extensions)

def select_extensions_interactively():
    available = get_available_extensions()
    if not available:
        print("No se encontraron archivos con extensiones reconocidas.")
        return []
    print(colored("\nExtensiones disponibles:", Colors.HEADER))
    print("=" * 60)
    for i, ext in enumerate(available, 1):
        lang = get_language(ext)
        print(f"{i:2d}. {ext:10} -> {lang}")
    print("\nOpciones: 'all', 'none', 'common', 'office' o números separados por comas.")
    while True:
        sel = input(colored("Tu selección: ", Colors.CYAN)).strip().lower()
        if sel == 'all':
            return available
        elif sel == 'none':
            return []
        elif sel == 'common':
            common = {'.py','.js','.jsx','.ts','.tsx','.java','.c','.cpp','.html','.css','.rb','.php','.go','.rs','.cs','.swift','.kt','.dart'}
            return [e for e in available if e in common]
        elif sel == 'office':
            office = {'.csv','.docx','.xlsx','.pptx','.odt','.ods','.odp','.pdf'}
            return [e for e in available if e in office]
        else:
            try:
                idxs = [int(x.strip()) for x in sel.split(',')]
                chosen = [available[i-1] for i in idxs if 1 <= i <= len(available)]
                if chosen:
                    return chosen
            except ValueError:
                pass
        print(colored("Selección no válida, intente otra vez.", Colors.WARNING))

def prompt_include_exclude():
    print(colored("\nFiltros adicionales (opcionales):", Colors.HEADER))
    inc = input("Patrón de inclusión (ej. test_*.py) [Enter = todos]: ").strip()
    exc = input("Patrón de exclusión (ej. *.min.*) [Enter = ninguno]: ").strip()
    return inc or None, exc or None

def prompt_compact_mode():
    resp = input(colored("¿Modo compacto (reducir espacios en blanco)? (s/n) [n]: ", Colors.CYAN)).strip().lower()
    return resp == 's' or resp == 'si'

def prompt_line_numbers():
    resp = input(colored("¿Incluir números de línea? (s/n) [n]: ", Colors.CYAN)).strip().lower()
    return resp == 's' or resp == 'si'

def select_output_format():
    print(colored("\nFormato de salida:", Colors.HEADER))
    print("1. Markdown (.md)")
    print("2. JSON (.json)")
    print("3. XML (.xml)")
    print("4. Texto plano (.txt)")
    print("5. Solo estadísticas (sin contenido de archivos)")
    print("6. Todos los formatos (md, json, xml, txt)")
    while True:
        choice = input(colored("Elige (1-6) [1]: ", Colors.CYAN)).strip()
        if choice in ('', '1'): return 'md'
        elif choice == '2': return 'json'
        elif choice == '3': return 'xml'
        elif choice == '4': return 'txt'
        elif choice == '5': return 'stats'
        elif choice == '6': return 'all'
        else: print(colored("Opción no válida.", Colors.WARNING))

def prompt_save_profile():
    resp = input(colored("¿Guardar este perfil para futuras ejecuciones? (s/n) [n]: ", Colors.CYAN)).strip().lower()
    return resp == 's' or resp == 'si'

def load_profile():
    if os.path.isfile('.context_profile.json'):
        if input(colored("¿Cargar perfil anterior? (s/n) [s]: ", Colors.CYAN)).strip().lower() not in ('n','no'):
            try:
                with open('.context_profile.json', 'r') as f:
                    return json.load(f)
            except:
                pass
    return None

def save_profile(profile):
    try:
        with open('.context_profile.json', 'w') as f:
            json.dump(profile, f, indent=2)
        print(colored("Perfil guardado.", Colors.GREEN))
    except Exception as e:
        logger.warning(f"No se pudo guardar perfil: {e}")

# ─── Compresión de contenido (compacto) ────────────────────────────────────
def compact_content(text):
    """Reduce múltiples líneas vacías consecutivas a una sola línea vacía."""
    lines = text.splitlines()
    compacted = []
    prev_empty = False
    for line in lines:
        if line.strip() == '':
            if not prev_empty:
                compacted.append('')
                prev_empty = True
        else:
            compacted.append(line)
            prev_empty = False
    return '\n'.join(compacted)

# ─── Escritura de salidas ──────────────────────────────────────────────────
def write_output_md(selected_extensions, tree_text, file_data, toc, compact, line_numbers, metadata, stats_md=''):
    output_file = 'context.md'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# CONTEXTO DEL PROYECTO\n\n")
        f.write(f"**Generado:** {metadata['generated']}  \n")
        f.write(f"**Sistema:** {metadata['system']} / {metadata['user']}  \n")
        f.write(f"**Directorio:** {metadata['root']}  \n")
        f.write(f"**Extensiones:** {', '.join(selected_extensions)}\n\n")
        if toc:
            f.write("## Índice de archivos\n\n")
            for item in toc:
                f.write(f"- [{item['path']}](#{item['anchor']})\n")
            f.write("\n---\n\n")
        f.write("## Estructura de directorios\n\n")
        f.write("```\n")
        f.write(tree_text)
        f.write("\n```\n\n---\n\n")
        f.write("## Contenido de archivos\n\n")
        for d in file_data:
            anchor = d['relative_path'].replace(' ', '-').replace('/', '-').replace('.', '')
            f.write(f"### <a name=\"{anchor}\"></a>./{d['relative_path']}\n")
            lang = d['language'].replace(' ', '-') if d['language'] else ''
            f.write(f"```{lang}\n")
            content = d['content']
            if not content.strip():
                f.write("[Archivo vacío]\n")
            else:
                if line_numbers:
                    lines = content.splitlines()
                    content = '\n'.join(f"{i+1:4d}: {line}" for i, line in enumerate(lines))
                f.write(content)
            f.write("\n```\n\n---\n\n")
        if stats_md:
            f.write("## Estadísticas finales\n\n")
            f.write(stats_md)
    return output_file

def write_output_json(selected_extensions, tree_text, file_data, metadata):
    output_file = 'context.json'
    data = {
        'metadata': metadata,
        'extensions': selected_extensions,
        'directory_tree': tree_text,
        'files': [{'path': d['relative_path'], 'language': d['language'], 'content': d['content']} for d in file_data]
    }
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return output_file

def write_output_xml(selected_extensions, tree_text, file_data, metadata):
    output_file = 'context.xml'
    root = ET.Element('context')
    ET.SubElement(root, 'generated').text = metadata['generated']
    ET.SubElement(root, 'system').text = metadata['system']
    ET.SubElement(root, 'user').text = metadata['user']
    ET.SubElement(root, 'directory').text = metadata['root']
    ET.SubElement(root, 'extensions').text = ', '.join(selected_extensions)
    tree_elem = ET.SubElement(root, 'directory_tree')
    tree_elem.text = tree_text
    files_elem = ET.SubElement(root, 'files')
    for d in file_data:
        fe = ET.SubElement(files_elem, 'file')
        ET.SubElement(fe, 'path').text = d['relative_path']
        ET.SubElement(fe, 'language').text = d['language']
        ET.SubElement(fe, 'content').text = d['content']
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(output_file, encoding='utf-8', xml_declaration=True)
    return output_file

def write_output_txt(selected_extensions, tree_text, file_data, metadata):
    output_file = 'context.txt'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"CONTEXTO DEL PROYECTO\nGenerado: {metadata['generated']}\nSistema: {metadata['system']}\n")
        f.write(f"Directorio: {metadata['root']}\nExtensiones: {', '.join(selected_extensions)}\n\n")
        f.write("ESTRUCTURA DE DIRECTORIOS\n")
        f.write(tree_text + "\n\n" + "="*50 + "\n\n")
        for d in file_data:
            f.write(f"./{d['relative_path']}\nLenguaje: {d['language']}\n")
            f.write(d['content'] if d['content'].strip() else "[Archivo vacío]\n")
            f.write("\n" + "="*50 + "\n\n")
    return output_file

# ─── Estadísticas ──────────────────────────────────────────────────────────
def compute_stats(file_data, omitted_files):
    total = len(file_data)
    total_lines = sum(d['content'].count('\n') for d in file_data)
    total_size = sum(os.path.getsize(os.path.join('.', d['relative_path'])) for d in file_data if os.path.isfile(os.path.join('.', d['relative_path'])))
    lang_counts = {}
    for d in file_data:
        lang = d['language']
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
    return {
        'total_files': total,
        'total_lines': total_lines,
        'total_size': format_size(total_size),
        'lang_counts': lang_counts,
        'omitted': omitted_files
    }

def format_stats_md(stats):
    md = f"- **Archivos procesados:** {stats['total_files']}\n"
    md += f"- **Líneas totales:** {stats['total_lines']}\n"
    md += f"- **Tamaño total:** {stats['total_size']}\n"
    md += f"- **Lenguajes:** {', '.join(f'{k} ({v})' for k,v in sorted(stats['lang_counts'].items(), key=lambda x: x[1], reverse=True))}\n"
    if stats['omitted']:
        md += "- **Archivos omitidos:**\n"
        for o in stats['omitted']:
            md += f"  - `{o['path']}`: {o['reason']}\n"
    return md

# ─── Main ──────────────────────────────────────────────────────────────────
def main():
    logger.info(colored("=== Generador de Contexto de Código ===", Colors.BOLD))

    # Intentar cargar perfil
    profile = load_profile()
    if profile:
        selected_extensions = profile.get('extensions', [])
        output_format = profile.get('format', 'md')
        compact_flag = profile.get('compact', False)
        line_numbers = profile.get('line_numbers', False)
        include_pat = profile.get('include_pat')
        exclude_pat = profile.get('exclude_pat')
        print(colored("Perfil cargado.", Colors.GREEN))
    else:
        selected_extensions = select_extensions_interactively()
        if not selected_extensions:
            logger.info("Sin extensiones, saliendo.")
            return
        output_format = select_output_format()
        include_pat, exclude_pat = prompt_include_exclude()
        compact_flag = prompt_compact_mode()
        line_numbers = prompt_line_numbers() if output_format in ('md', 'all') else False
        profile = {
            'extensions': selected_extensions,
            'format': output_format,
            'compact': compact_flag,
            'line_numbers': line_numbers,
            'include_pat': include_pat,
            'exclude_pat': exclude_pat
        }
        if prompt_save_profile():
            save_profile(profile)

    # Cargar .contextignore
    context_patterns = load_contextignore()
    # Cargar .gitignore
    git_spec = None
    if HAS_PATHSPEC and os.path.isfile('.gitignore'):
        try:
            with open('.gitignore', 'r', encoding='utf-8') as f:
                lines = f.read().splitlines()
            git_spec = pathspec.PathSpec.from_lines('gitwildmatch', lines)
        except Exception as e:
            logger.warning(f"No se pudo procesar .gitignore: {e}")

    # Generar árbol
    logger.info(colored("Generando árbol de directorios...", Colors.CYAN))
    tree_text = generate_directory_tree('.', context_patterns, git_spec)

    # Buscar archivos con filtros
    file_list = []
    for root, dirs, files in os.walk('.', followlinks=False):
        dirs[:] = [d for d in dirs if not should_ignore_dir_basic(d) and
                   not should_ignore_by_contextignore(os.path.relpath(os.path.join(root, d), '.') + '/', context_patterns) and
                   not (git_spec and is_ignored_by_gitignore(os.path.relpath(os.path.join(root, d), '.'), git_spec))]
        for filename in files:
            filepath = os.path.join(root, filename)
            if os.path.islink(filepath):
                continue
            rel = os.path.relpath(filepath, '.')
            if git_spec and is_ignored_by_gitignore(rel, git_spec):
                continue
            if should_ignore_by_contextignore(rel, context_patterns):
                continue
            _, ext = os.path.splitext(filename)
            ext = ext.lower()
            if ext not in selected_extensions or ext not in language_map:
                continue
            base = os.path.basename(filepath)
            if include_pat and not fnmatch.fnmatch(base, include_pat):
                continue
            if exclude_pat and fnmatch.fnmatch(base, exclude_pat):
                continue
            lang = get_language(ext)
            file_list.append((filepath, rel, lang))

    total_files = len(file_list)
    logger.info(colored(f"Archivos a procesar: {total_files}", Colors.CYAN))

    # Modo solo estadísticas
    if output_format == 'stats':
        stats_data = []
        for filepath, rel, lang in file_list:
            try:
                size = os.path.getsize(filepath)
                stats_data.append({'relative_path': rel, 'language': lang, 'size': size})
            except:
                pass
        stats = {
            'total_files': len(stats_data),
            'total_lines': 0,
            'total_size': format_size(sum(d['size'] for d in stats_data)),
            'lang_counts': {},
            'omitted': []
        }
        for d in stats_data:
            lang = d['language']
            stats['lang_counts'][lang] = stats['lang_counts'].get(lang, 0) + 1
        stats_output = {
            'metadata': {
                'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'system': platform.platform(),
                'user': getpass.getuser(),
                'root': os.path.abspath('.')
            },
            'extensions': selected_extensions,
            'stats': stats
        }
        with open('context_stats.json', 'w', encoding='utf-8') as f:
            json.dump(stats_output, f, indent=2, ensure_ascii=False)
        print(colored("\nEstadísticas exportadas a context_stats.json", Colors.GREEN))
        return

    # Procesamiento concurrente de archivos
    file_data = [None] * total_files
    omitted_files = []

    if HAS_TQDM:
        pbar = tqdm(total=total_files, desc="Procesando", unit="archivo")
    else:
        pbar = None

    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_idx = {}
        for idx, (filepath, rel, lang) in enumerate(file_list):
            future = executor.submit(read_file_content, filepath)
            future_to_idx[future] = idx
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            filepath, rel, lang = file_list[idx]
            content = future.result()
            if content.startswith("[Archivo binario") or content.startswith("[Posible archivo binario") or content.startswith("[Error") or content.startswith("[No se pudo"):
                omitted_files.append({'path': rel, 'reason': content})
                continue
            if compact_flag:
                content = compact_content(content)
            file_data[idx] = {
                'relative_path': rel,
                'language': lang,
                'content': content
            }
            if pbar:
                pbar.update(1)
    if pbar:
        pbar.close()

    # Filtrar Nones (omitidos)
    file_data = [d for d in file_data if d is not None]

    # TOC solo para MD
    toc = [{'path': d['relative_path'], 'anchor': d['relative_path'].replace(' ', '-').replace('/', '-').replace('.', '')} for d in file_data]

    metadata = {
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'system': platform.platform(),
        'user': getpass.getuser(),
        'root': os.path.abspath('.')
    }

    stats = compute_stats(file_data, omitted_files)
    stats_md = format_stats_md(stats)

    # Determinar lista de formatos a generar
    if output_format == 'all':
        formats_to_generate = ['md', 'json', 'xml', 'txt']
    else:
        formats_to_generate = [output_format]

    generated_files = []
    for fmt in formats_to_generate:
        if fmt == 'md':
            out = write_output_md(selected_extensions, tree_text, file_data, toc, compact_flag, line_numbers, metadata, stats_md)
        elif fmt == 'json':
            out = write_output_json(selected_extensions, tree_text, file_data, metadata)
        elif fmt == 'xml':
            out = write_output_xml(selected_extensions, tree_text, file_data, metadata)
        elif fmt == 'txt':
            out = write_output_txt(selected_extensions, tree_text, file_data, metadata)
        generated_files.append(out)

    # Exportar estadísticas aparte
    stats_file = 'context_stats.json'
    stats_export = {
        'metadata': metadata,
        'extensions': selected_extensions,
        'stats': {
            'total_files': stats['total_files'],
            'total_lines': stats['total_lines'],
            'total_size': stats['total_size'],
            'languages': stats['lang_counts'],
            'omitted': [{'path': o['path'], 'reason': o['reason']} for o in omitted_files]
        }
    }
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(stats_export, f, indent=2, ensure_ascii=False)
    print(colored(f"Estadísticas exportadas a {stats_file}", Colors.GREEN))

    # Resumen final
    print(colored("\n=== RESUMEN ===", Colors.BOLD))
    print(f"Archivos generados: {', '.join(generated_files)}")
    print(f"Archivos procesados: {stats['total_files']}")
    print(f"Líneas totales: {stats['total_lines']}")
    print(f"Tamaño total: {stats['total_size']}")
    print("Lenguajes:", ', '.join(f"{k} ({v})" for k,v in sorted(stats['lang_counts'].items(), key=lambda x: x[1], reverse=True)))
    if omitted_files:
        print(colored("Archivos omitidos:", Colors.WARNING))
        for o in omitted_files:
            print(f"  {o['path']} -> {o['reason']}")

if __name__ == '__main__':
    main()