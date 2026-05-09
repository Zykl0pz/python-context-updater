# Generador de Contexto de Código

Script interactivo en Python para generar un documento de contexto del proyecto, ideal para alimentar modelos de lenguaje o para documentación rápida. Analiza el directorio actual, muestra un árbol de archivos con tamaños, y extrae el contenido de los archivos según las extensiones que elijas, exportándolo en diversos formatos (Markdown, JSON, XML, texto plano o solo estadísticas).

## Requisitos

- Python 3.7 o superior.

### Dependencias opcionales

El script funciona perfectamente sin ellas, pero instalar alguna amplía sus capacidades:

| Librería              | Mejora                                                               | Instalación                         |
|-----------------------|----------------------------------------------------------------------|-------------------------------------|
| `charset-normalizer`  | Detección precisa de la codificación de archivos                     | `pip install charset-normalizer`    |
| `pathspec`            | Soporte para reglas `.gitignore`                                     | `pip install pathspec`              |
| `tqdm`                | Barra de progreso durante el procesamiento                           | `pip install tqdm`                  |
| `PyPDF2` o `pdfplumber` | Extracción de texto de archivos PDF                                  | `pip install PyPDF2` o `pip install pdfplumber` |

## Uso

1. Coloca el script `context.py` en la raíz del proyecto que deseas analizar.
2. Ejecuta:

   ```bash
   python context.py
   ```

3. Sigue las instrucciones interactivas:
   - Selecciona las extensiones de archivo que quieres incluir (por números, `all`, `common`, `office`).
   - Opcionalmente, define patrones de inclusión/exclusión (por ejemplo, `test_*.py` o `*.min.*`).
   - Elige el formato de salida: Markdown, JSON, XML, texto plano, solo estadísticas o **todos los formatos**.
   - Indica si deseas modo compacto y/o números de línea (para Markdown).
   - Decide si guardar la configuración como perfil para futuras ejecuciones.
4. El resultado se generará en uno o varios archivos:
   - `context.md` / `context.json` / `context.xml` / `context.txt` según el formato elegido.
   - `context_stats.json` con las estadísticas detalladas (siempre, excepto en modo solo estadísticas, en cuyo caso solo se genera este archivo).
   - `context.log` con información de depuración.

### Ejemplo de flujo

```
=== Generador de Contexto de Código ===

Extensiones disponibles:
 1. .py        -> Python
 2. .js        -> JavaScript
 ...
 Tu selección: all

 Formato de salida:
 1. Markdown (.md)
 2. JSON (.json)
 3. XML (.xml)
 4. Texto plano (.txt)
 5. Solo estadísticas (sin contenido de archivos)
 6. Todos los formatos (md, json, xml, txt)
 Elige (1-6) [1]: 6

 ¿Modo compacto? (s/n) [n]: s
 ¿Incluir números de línea? (s/n) [n]:
 ¿Guardar este perfil para futuras ejecuciones? (s/n) [n]: s

 ... (procesamiento) ...

 === RESUMEN ===
 Archivos generados: context.md, context.json, context.xml, context.txt
 Archivos procesados: 42
 Líneas totales: 5783
 Tamaño total: 2.1 MB
 Lenguajes: Python (25), JavaScript (10), Markdown (7)
```

## Instalación como comando global (`getcurrentcontext`)

Para ejecutar la herramienta con un simple `getcurrentcontext` desde cualquier carpeta de proyecto, sigue estos pasos:

### Linux / macOS

1. **Asigna permisos de ejecución** al script y asegúrate de que tenga un *shebang* al inicio.  
   El script ya incluye `#!/usr/bin/env python3` al comienzo; si no fuera así, añade esa línea como primera línea del archivo.  
   Luego, hazlo ejecutable:

   ```bash
   chmod +x /ruta/completa/context.py
   ```

2. **Crea un alias** en tu archivo de configuración de shell (`.bashrc`, `.bash_aliases`, `.zshrc`, etc.).  
   Abre el archivo correspondiente con un editor y añade la siguiente línea:

   ```bash
   alias getcurrentcontext='python /ruta/completa/context.py'
   ```

   > Nota: reemplaza `/ruta/completa/` por la ubicación real del script.

   *Alternativa con el shebang* (si lo hiciste ejecutable):

   ```bash
   alias getcurrentcontext='/ruta/completa/context.py'
   ```

3. **Recarga la configuración** o abre una nueva terminal:

   ```bash
   source ~/.bashrc
   ```

4. **Uso**: navega a la carpeta del proyecto que quieres analizar y ejecuta:

   ```bash
   getcurrentcontext
   ```

### Windows

#### Opción A: archivo batch (.bat)

1. Crea un archivo `getcurrentcontext.bat` en una carpeta que esté en el PATH (por ejemplo, `C:\Windows` o una carpeta personalizada que añadas al PATH).  
   Contenido del archivo:

   ```batch
   @echo off
   python "C:\ruta\completa\context.py" %*
   ```

2. Ahora podrás ejecutar desde cualquier carpeta:

   ```cmd
   getcurrentcontext
   ```

#### Opción B: alias en PowerShell

1. Abre PowerShell y edita tu perfil (si no existe, créalo):

   ```powershell
   notepad $PROFILE
   ```

2. Añade la función:

   ```powershell
   function getcurrentcontext {
       python "C:\ruta\completa\context.py"
   }
   ```

3. Guarda y recarga el perfil:

   ```powershell
   . $PROFILE
   ```

4. Ejecuta `getcurrentcontext` dentro de la carpeta del proyecto.

> **Importante:** En todos los casos, el comando debe ejecutarse desde la raíz del proyecto que se desea analizar. El script siempre toma el directorio actual como punto de partida.

## Archivos de configuración

### `.contextignore`

Al ejecutar el script por primera vez se crea automáticamente un archivo `.contextignore` con una lista de directorios ignorados por defecto (como `__pycache__`, `node_modules`, `.git`, etc.). Puedes editarlo para añadir más patrones (uno por línea). Se admiten patrones estilo glob y directorios terminados en `/`.

Ejemplo de `.contextignore`:

```
# Carpetas ignoradas por defecto
__pycache__/
node_modules/
dist/
.vscode/

# Añade tus propias reglas
*.log
temp/
```

### `.context_profile.json`

Cuando decides guardar un perfil, se crea este archivo con la última configuración utilizada. En futuras ejecuciones se te preguntará si deseas cargarlo, ahorrando tiempo en selecciones repetitivas.

## Formatos de salida

- **Markdown** (`context.md`): incluye metadatos, TOC, árbol de directorios y contenido de cada archivo en bloques de código con resaltado de sintaxis. Ideal para prompts de IA.
- **JSON** (`context.json`): estructura anidada con metadatos, árbol y lista de archivos. Útil para procesamiento automatizado.
- **XML** (`context.xml`): similar a JSON pero en formato XML.
- **Texto plano** (`context.txt`): formato simple sin marcado.
- **Solo estadísticas** (`context_stats.json`): no extrae contenidos, solo genera un archivo JSON con el resumen de archivos, tamaños y extensiones.
- **Todos los formatos**: genera simultáneamente los cuatro archivos principales (md, json, xml, txt) junto con el de estadísticas.

## Notas adicionales

- Los **enlaces simbólicos** se ignoran para evitar recursividad y duplicados.
- Los **archivos binarios** se detectan automáticamente (byte nulo + heurística de caracteres de control) y se omiten, registrándose en el log.
- Los **archivos vacíos** se incluyen explícitamente con la etiqueta `[Archivo vacío]`.
- La barra de progreso solo aparece si `tqdm` está instalado; en caso contrario se muestran mensajes simples.
- La detección de encoding usa la caché interna para no re-leer archivos repetidamente.
- La salida coloreada se desactiva automáticamente si la salida no es una terminal (ej. al redirigir a un archivo).

## Solución de problemas

- Si faltan las librerías opcionales, el script lo indicará al inicio con un aviso (`⚠️`) y continuará con el comportamiento por defecto.
- Si algún archivo no se puede leer (permisos, corrupción), se registra en `context.log` y se muestra en la lista de omitidos al final.
- Para PDFs sin librerías instaladas, se indicará `[PDF no procesado (instala PyPDF2 o pdfplumber)]`.

## Licencia

Este proyecto se distribuye bajo la licencia MIT. Siéntete libre de modificarlo y compartirlo.
