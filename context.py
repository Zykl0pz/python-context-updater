import os
import zipfile
import xml.etree.ElementTree as ET
import csv

# Mapa de extensiones a lenguajes de programación
language_map = {
    '.py': 'Python',
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
    '.sh': 'Shell script (Bash)',
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
    '.ps1': 'Powershell',
    '.sql': 'SQL',
    '.sol': 'Solidity',
    '.bas': 'VBA',
    '.cls': 'VBA',
    '.frm': 'VBA',
    '.m': 'MATLAB',
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
}

# Lista de encodings comunes a probar (en orden de probabilidad)
COMMON_ENCODINGS = [
    'utf-8',
    'latin-1',
    'cp1252',
    'iso-8859-1',
    'utf-16',
    'cp437',
    'ascii'
]

def get_language(extension):
    return language_map.get(extension, 'Texto')

def read_csv_content(filepath):
    """Lee el contenido de un archivo CSV y lo convierte a texto legible"""
    try:
        content = []
        # Probar diferentes encodings para CSV
        for encoding in COMMON_ENCODINGS:
            try:
                with open(filepath, 'r', encoding=encoding, newline='') as csvfile:
                    csv_reader = csv.reader(csvfile)
                    for i, row in enumerate(csv_reader):
                        content.append(f"Fila {i+1}: {', '.join(row)}")
                return '\n'.join(content)
            except (UnicodeDecodeError, UnicodeError):
                continue
        return "[No se pudo leer el archivo CSV con ningún encoding compatible]"
    except Exception as e:
        return f"[Error leyendo archivo CSV: {str(e)}]"

def read_docx_content(filepath):
    """Extrae texto de un archivo DOCX"""
    try:
        with zipfile.ZipFile(filepath) as docx:
            # El contenido principal está en word/document.xml
            if 'word/document.xml' in docx.namelist():
                with docx.open('word/document.xml') as document_file:
                    tree = ET.parse(document_file)
                    root = tree.getroot()
                    
                    # Namespace para documentos Word
                    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                    
                    # Extraer todos los párrafos
                    paragraphs = []
                    for paragraph in root.findall('.//w:p', ns):
                        texts = []
                        for text_elem in paragraph.findall('.//w:t', ns):
                            if text_elem.text:
                                texts.append(text_elem.text)
                        if texts:
                            paragraphs.append(''.join(texts))
                    
                    return '\n'.join(paragraphs)
            else:
                return "[Estructura DOCX no reconocida]"
    except Exception as e:
        return f"[Error leyendo archivo DOCX: {str(e)}]"

def read_xlsx_content(filepath):
    """Extrae texto de un archivo XLSX (solo valores de celdas)"""
    try:
        with zipfile.ZipFile(filepath) as xlsx:
            # Primero, obtener los strings compartidos si existen
            shared_strings = []
            if 'xl/sharedStrings.xml' in xlsx.namelist():
                with xlsx.open('xl/sharedStrings.xml') as shared_strings_file:
                    tree = ET.parse(shared_strings_file)
                    root = tree.getroot()
                    ns = {'': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                    
                    for string_elem in root.findall('.//t', ns):
                        if string_elem.text:
                            shared_strings.append(string_elem.text)
            
            # Buscar en todas las hojas de cálculo
            sheets_content = []
            sheet_files = [name for name in xlsx.namelist() 
                          if name.startswith('xl/worksheets/sheet') and name.endswith('.xml')]
            
            for sheet_file in sheet_files:
                with xlsx.open(sheet_file) as sheet_file_obj:
                    tree = ET.parse(sheet_file_obj)
                    root = tree.getroot()
                    ns = {'': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                    
                    # Extraer valores de celdas
                    sheet_data = []
                    for cell in root.findall('.//c', ns):
                        value_elem = cell.find('.//v', ns)
                        if value_elem is not None and value_elem.text:
                            # Si es un string compartido
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
    """Extrae texto de un archivo PPTX"""
    try:
        with zipfile.ZipFile(filepath) as pptx:
            # Buscar en todas las diapositivas
            slides_content = []
            slide_files = [name for name in pptx.namelist() 
                          if name.startswith('ppt/slides/slide') and name.endswith('.xml')]
            
            for slide_file in slide_files:
                with pptx.open(slide_file) as slide_file_obj:
                    tree = ET.parse(slide_file_obj)
                    root = tree.getroot()
                    
                    # Namespace para presentaciones
                    ns = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
                    
                    # Extraer texto de la diapositiva
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

def read_file_content(filepath):
    """Lee el contenido de un archivo probando múltiples encodings o métodos específicos"""
    _, ext = os.path.splitext(filepath)
    ext = ext.lower()
    
    # Archivos especiales que requieren procesamiento específico
    if ext == '.csv':
        return read_csv_content(filepath)
    elif ext == '.docx':
        return read_docx_content(filepath)
    elif ext == '.xlsx':
        return read_xlsx_content(filepath)
    elif ext == '.pptx':
        return read_pptx_content(filepath)
    else:
        # Para el resto de archivos, usar el método de probar encodings
        try:
            with open(filepath, 'rb') as f:
                raw_data = f.read(1024)
                
            # Detectar archivos binarios
            if b'\x00' in raw_data:
                return "[Archivo binario - omitido]"
        except Exception:
            return "[Error accediendo al archivo]"
        
        # Probar diferentes encodings
        for encoding in COMMON_ENCODINGS:
            try:
                with open(filepath, 'r', encoding=encoding) as file:
                    content = file.read()
                    # Verificar si hay muchos caracteres de control (posible archivo binario)
                    control_chars = sum(1 for char in content if ord(char) < 32 and char not in '\n\r\t')
                    if control_chars > len(content) * 0.1:
                        continue
                    return content
            except (UnicodeDecodeError, UnicodeError):
                continue
            except Exception:
                continue
        
        # Último intento con manejo de errores
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as file:
                return file.read()
        except Exception:
            return "[No se pudo leer el archivo con ningún encoding compatible]"

def get_available_extensions():
    """Obtiene todas las extensiones disponibles en el directorio actual que están en language_map"""
    extensions = set()
    
    for root, dirs, files in os.walk('.'):
        # Filtrar carpetas ocultas y de sistema
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__' and d != 'node_modules' and d != 'dist']
        
        for filename in files:
            filepath = os.path.join(root, filename)
            if os.path.isfile(filepath):
                _, ext = os.path.splitext(filename)
                # Solo agregar si tiene extensión Y está en el language_map
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
    print("  - 'office' para seleccionar extensiones de Office (docx, xlsx, pptx, csv)")
    
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
            office_exts = {'.csv', '.docx', '.xlsx', '.pptx'}
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

def main():
    output_file = 'context.md'
    
    print("Generador de Contexto de Código")
    print("=" * 40)
    print("Este script analizará el directorio actual y generará un archivo 'context.md'")
    print("con el contenido de los archivos que selecciones.\n")
    
    # Selección interactiva de extensiones
    selected_extensions = select_extensions_interactively()
    
    if not selected_extensions:
        print("No se seleccionaron extensiones. Saliendo...")
        return
    
    print(f"\nExtensiones seleccionadas: {', '.join(selected_extensions)}")
    print("Procesando archivos...")
    
    file_count = 0
    
    with open(output_file, 'w', encoding='utf-8') as outfile:
        # Escribir cabecera con información de las extensiones seleccionadas
        outfile.write("CONTEXTO DEL PROYECTO\n")
        outfile.write("=" * 50 + "\n")
        outfile.write(f"Extensiones incluidas: {', '.join(selected_extensions)}\n")
        outfile.write("=" * 50 + "\n\n")
        
        for root, dirs, files in os.walk('.'):
            # Filtrar carpetas ocultas y de sistema
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__' and d != 'node_modules' and d != 'dist']
            
            for filename in files:
                filepath = os.path.join(root, filename)
                
                if os.path.isfile(filepath):
                    _, ext = os.path.splitext(filename)
                    
                    # Verificar si la extensión está en las seleccionadas Y en el language_map
                    if ext.lower() in selected_extensions and ext.lower() in language_map:
                        language = get_language(ext)
                        
                        # Ruta relativa para mostrar
                        relative_path = os.path.relpath(filepath, start='.')
                        
                        # Escribir encabezado
                        outfile.write(f'./{relative_path}\n')
                        outfile.write(f'`{language}\n')
                        
                        # Leer y escribir contenido
                        content = read_file_content(filepath)
                        outfile.write(content)
                        
                        # Cerrar bloque
                        outfile.write('`\n\n')
                        file_count += 1
    
    print(f"\n¡Proceso completado!")
    print(f"Se procesaron {file_count} archivos.")
    print(f"Resultado guardado en: {output_file}")

if __name__ == '__main__':
    main()
