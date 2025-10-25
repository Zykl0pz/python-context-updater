import os

# Mapa de extensiones a lenguajes de programación
language_map = {
    '.py': 'Python',
    '.feature': 'Feature',
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
    # XPath no tiene extensión específica
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
}

def get_language(extension):
    return language_map.get(extension, 'Texto')

def main():
    output_file = 'context.txt'

    with open(output_file, 'w', encoding='utf-8') as outfile:
        for root, dirs, files in os.walk('.'):
            # Opcional: eliminar carpetas ocultas o .git si lo deseas
            # Ejemplo: evitar carpeta .git
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']

            for filename in files:
                filepath = os.path.join(root, filename)
                
                # Saltar rutas que puedan ser carpetas (aunque en os.walk ya están filtradas)
                if os.path.isfile(filepath):
                    _, ext = os.path.splitext(filename)
                    language = get_language(ext)

                    # Ruta relativa para mostrar
                    relative_path = os.path.relpath(filepath, start='.')

                    # Escribir encabezado
                    outfile.write(f'./{relative_path}\n')
                    outfile.write(f'`{language}\n')

                    try:
                        with open(filepath, 'r', encoding='utf-8') as infile:
                            content = infile.read()
                            outfile.write(content)
                    except UnicodeDecodeError:
                        outfile.write('[Contenido no legible como UTF-8 (archivo binario o codificación diferente)]')

                    # Cerrar bloque
                    outfile.write('`\n\n')

if __name__ == '__main__':
    main()
