# Context Code Generator

Un script de Python que genera un archivo de contexto unificado (`context.txt`) a partir de los archivos de código y documentos en tu proyecto. Perfecto para proporcionar contexto a herramientas de IA, documentación o análisis de proyectos.

## 🚀 Características

- **Análisis completo de directorios**: Recorre recursivamente todos los subdirectorios
- **Selección interactiva**: Elige qué extensiones de archivo incluir mediante un menú interactivo
- **Múltiples formatos soportados**:
  - **Código fuente**: Python, JavaScript, Java, C++, HTML, CSS, y [muchos más](#-lenguajes-soportados)
  - **Documentos de Office**: DOCX, XLSX, PPTX, CSV
  - **Archivos de configuración**: YAML, JSON, XML, etc.
- **Detección automática de encoding**: Lee archivos con diferentes codificaciones sin problemas
- **Sin dependencias externas**: Usa solo módulos estándar de Python
- **Filtrado inteligente**: Omite automáticamente carpetas ocultas y archivos binarios

## 📋 Lenguajes Soportados

El script reconoce más de 70 extensiones de archivo, incluyendo:

- **Lenguajes de programación**: Python, JavaScript, Java, C/C++, Rust, Go, Ruby, PHP, etc.
- **Lenguajes web**: HTML, CSS, TypeScript, JSX, TSX
- **Lenguajes funcionales**: Haskell, Elixir, Clojure, F#, OCaml
- **Scripting**: Bash, PowerShell, Perl, Lua, Ruby
- **Documentación**: Markdown, Texto, YAML
- **Office**: DOCX, XLSX, PPTX, CSV

[Ver lista completa de extensiones soportadas](https://github.com/tu-usuario/context-code-generator/blob/main/context.py#L4-L75)

## 🛠️ Instalación

1. **Clona el repositorio**:
   ```bash
   git clone https://github.com/tu-usuario/context-code-generator.git
   cd context-code-generator
   ```

2. **Asegúrate de tener Python 3.6+**:
   ```bash
   python --version
   ```

No se requieren dependencias externas. El script usa solo módulos estándar de Python.

## 📖 Uso

### Uso Básico

1. **Navega a tu proyecto**:
   ```bash
   cd /ruta/a/tu/proyecto
   ```

2. **Ejecuta el script**:
   ```bash
   python /ruta/al/script/context.py
   ```

3. **Sigue el menú interactivo**:
   - Verás todas las extensiones disponibles en tu proyecto
   - Selecciona usando números separados por comas
   - Opciones especiales: `all`, `none`, `common`, `office`

4. **Encuentra el resultado**:
   - El archivo `context.txt` se generará en el directorio actual
   - Contiene todo el código y contenido seleccionado en formato estructurado

### Opciones de Selección

- **Números individuales**: `1,3,5` - Selecciona extensiones específicas
- **`all`**: Incluye todas las extensiones reconocidas
- **`none`**: No incluye ninguna extensión (sale del programa)
- **`common`**: Selecciona extensiones comunes de programación
- **`office`**: Selecciona solo documentos de Office (DOCX, XLSX, PPTX, CSV)

### Ejemplo de Sesión

```bash
$ python context.py

Generador de Contexto de Código
========================================
Este script analizará el directorio actual y generará un archivo 'context.txt'
con el contenido de los archivos que selecciones.

Extensiones disponibles en el directorio (solo las reconocidas):
============================================================
 1. .py        -> Python
 2. .js        -> JavaScript
 3. .html      -> HTML
 4. .css       -> CSS
 5. .json      -> JSON
 6. .md        -> Markdown
 7. .docx      -> Word Document

Opciones:
  - Ingresa los números de las extensiones separados por comas (ej: 1,3,5)
  - 'all' para seleccionar todas las extensiones
  - 'none' para no seleccionar ninguna
  - 'common' para seleccionar extensiones comunes de código
  - 'office' para seleccionar extensiones de Office (docx, xlsx, pptx, csv)

Tu selección: common
```

## 📁 Estructura del Output

El archivo `context.txt` generado tiene el siguiente formato:

```
CONTEXTO DEL PROYECTO
==================================================
Extensiones incluidas: .py, .js, .html

./src/main.py
`Python
# Contenido del archivo main.py
`

./src/utils.js
`JavaScript
// Contenido del archivo utils.js
`

./documentacion.docx
`Word Document
Texto extraído del documento Word...
`
```

## 🔧 Personalización

### Agregar Nuevas Extensiones

Edita el diccionario `language_map` en el script para agregar nuevas extensiones:

```python
language_map = {
    '.nuevo': 'Nuevo Lenguaje',
    # ... extensiones existentes
}
```

### Excluir Carpetas

El script excluye automáticamente:
- Carpetas que comienzan con `.` (ocultas)
- `__pycache__`
- `node_modules` (si existe)

Para agregar más exclusiones, modifica la línea:
```python
dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
```

## ⚠️ Limitaciones

- **Archivos binarios**: Se detectan y omiten automáticamente
- **Archivos de Office complejos**: Solo se extrae texto básico (sin formato, imágenes, etc.)
- **Encoding muy raro**: Puede haber problemas con codificaciones poco comunes
- **Archivos muy grandes**: Pueden ser lentos de procesar

## 🐛 Solución de Problemas

### Error: "No se encontraron archivos con extensiones reconocidas"
- Verifica que el directorio contenga archivos con extensiones conocidas
- Revisa que no estés en un directorio vacío o solo con archivos binarios

### Error de encoding
- El script intenta automáticamente múltiples codificaciones
- Si falla, el contenido se marca como no legible

### El archivo de salida está vacío
- Verifica que hayas seleccionado extensiones existentes en el proyecto
- Comprueba los permisos de escritura en el directorio

## 🤝 Contribuciones

Las contribuciones son bienvenidas. Puedes:

1. Reportar bugs o sugerir nuevas características
2. Agregar soporte para más extensiones de archivo
3. Mejorar la detección de encoding
4. Optimizar el rendimiento para proyectos grandes

## 📄 Licencia

Este proyecto está bajo la Licencia MIT. Ver el archivo `LICENSE` para más detalles.

---

**¿Te resulta útil este script?** ¡Dale una ⭐ al repositorio!
