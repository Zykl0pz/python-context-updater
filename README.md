# Conjunto de Herramientas para Desarrolladores

## Índice

- [Conjunto de Herramientas para Desarrolladores](#conjunto-de-herramientas-para-desarrolladores)
  - [Índice](#índice)
  - [Presentación](#presentación)
  - [Instalación y configuración inicial](#instalación-y-configuración-inicial)
    - [Clonación](#clonación)
    - [Entorno virtual y dependencias](#entorno-virtual-y-dependencias)
      - [Dependencias principales](#dependencias-principales)
      - [Uso rápido](#uso-rápido)
  - [Herramientas disponibles](#herramientas-disponibles)
    - [`context.py` – Generador de contexto de código](#contextpy--generador-de-contexto-de-código)
    - [`list_packages.py` – Listado de paquetes instalados](#list_packagespy--listado-de-paquetes-instalados)
    - [`rename.py` – Renombrador interactivo de archivos](#renamepy--renombrador-interactivo-de-archivos)
    - [`sort.py` – Ordenador con índice numérico](#sortpy--ordenador-con-índice-numérico)
    - [`classify.py` – Clasificador automático por tipo](#classifypy--clasificador-automático-por-tipo)
    - [`compress_to_path.py` – Compresor/descompresor inteligente](#compress_to_pathpy--compresordescompresor-inteligente)
    - [`http_server.py` – Servidor HTTP con interfaz web](#http_serverpy--servidor-http-con-interfaz-web)
    - [`file_sharing_server.py` – Servidor con subida de archivos](#file_sharing_serverpy--servidor-con-subida-de-archivos)
    - [`git_diff_context.py` – Generador de diferencias Git](#git_diff_contextpy--generador-de-diferencias-git)
  - [Arquitectura y decisiones de diseño](#arquitectura-y-decisiones-de-diseño)
    - [Gestión de rutas con `path_manager.py`](#gestión-de-rutas-con-path_managerpy)
    - [Sistema de perfiles y persistencia](#sistema-de-perfiles-y-persistencia)
    - [Logging y trazabilidad](#logging-y-trazabilidad)
    - [Manejo de codificaciones y archivos binarios](#manejo-de-codificaciones-y-archivos-binarios)
    - [Concurrencia y rendimiento](#concurrencia-y-rendimiento)
    - [Formatos de salida y extensibilidad](#formatos-de-salida-y-extensibilidad)
    - [Integración con `.gitignore` y `.contextignore`](#integración-con-gitignore-y-contextignore)
    - [Modo deshacer (undo)](#modo-deshacer-undo)
  - [Licencia](#licencia)

---

## Presentación

Este repositorio agrupa un conjunto de herramientas de línea de comandos diseñadas para agilizar tareas comunes en el día a día del desarrollo de software. Cada script es **autónomo** y resuelve un problema específico, pero todos comparten una base común de organización, persistencia de configuración y gestión de logs que facilita su uso y mantenimiento.

Las herramientas cubren desde la generación de documentación contextual de un proyecto (para alimentar modelos de lenguaje o revisiones) hasta la ordenación y renombrado masivo de archivos, pasando por la compresión inteligente, servidores HTTP interactivos y la extracción de diferencias Git.

El repositorio está escrito íntegramente en **Python 3.7+** y está diseñado para ser multiplataforma (Linux, macOS, Windows), aunque algunas funcionalidades (gestores de paquetes, metadatos Unix) dependen del sistema operativo.

---

## Instalación y configuración inicial

### Clonación

```bash
git clone https://github.com/tu-usuario/python-context-updater.git
cd python-context-updater
```

### Entorno virtual y dependencias

El proyecto incluye dos scripts para preparar el entorno:

- **`bootstrap.py`** – Crea un entorno virtual (`venv/`), genera el archivo `requirements.txt` con las dependencias necesarias y las instala mostrando el progreso en tiempo real. Al finalizar ofrece un menú interactivo para ejecutar cualquiera de las herramientas.
- **`start.py`** – Similar a `bootstrap.py`, pero más orientado a ser un lanzador principal. También crea el venv, instala dependencias y permite elegir el script a ejecutar, ya sea mediante menú o pasando el nombre del script como argumento.

#### Dependencias principales

- `tqdm` – Barras de progreso.
- `charset-normalizer` – Detección robusta de codificaciones.
- `pathspec` – Soporte para `.gitignore`.
- `py7zr` – Manejo de archivos 7z.
- `pyzipper` – Compresión ZIP con contraseña (AES).
- `send2trash` – Envío a la papelera de reciclaje.
- `PyPDF2` / `pdfplumber` – Extracción de texto de PDF.
- `pygments` – Resaltado de sintaxis para HTML.
- `pyperclip` – Copia al portapapeles (opcional).

#### Uso rápido

```bash
python3 bootstrap.py
```

O, si prefieres lanzar directamente una herramienta:

```bash
python3 start.py context.py
```

Ambos scripts se encargan de activar el entorno virtual y de instalar cualquier dependencia que falte.

> **Nota:** Los scripts también se pueden ejecutar sin el venv, siempre que las dependencias estén instaladas globalmente. Sin embargo, se recomienda usar el venv para evitar conflictos.

---

## Herramientas disponibles

### `context.py` – Generador de contexto de código

**Propósito:**  
Analiza el directorio actual, genera un árbol de directorios con tamaños y extrae el contenido de los archivos según las extensiones seleccionadas. El resultado puede exportarse en Markdown, JSON, XML, TXT o solo estadísticas. Es ideal para documentar la estructura de un proyecto, preparar entradas para LLMs o hacer revisiones de código.

**Uso básico:**

```bash
python3 context.py
```

Por defecto inicia un **modo interactivo** que permite:

- Seleccionar extensiones a incluir (de entre las detectadas en el directorio).
- Configurar filtros de inclusión/exclusión por patrón glob.
- Elegir el formato de salida (incluyendo la opción `all` para generar todos los formatos a la vez).
- Activar modo compacto (elimina líneas vacías consecutivas) y números de línea.
- Decidir si mostrar archivos ocultos en el árbol.

**Opciones de línea de comandos** (no implementadas directamente, pero se pueden usar mediante perfiles o paso de argumentos en modo no interactivo).

**Características destacadas:**

- **Detección de codificación:** Usa `charset-normalizer` para detectar la codificación de los archivos de texto; si no está disponible, recurre a una lista de codificaciones comunes.
- **Lectura de formatos especiales:** Extrae texto de archivos DOCX, XLSX, PPTX, ODT, ODS, ODP, IPYNB y PDF (requiere las librerías correspondientes).
- **Respeto de `.contextignore`:** Ignora directorios como `__pycache__`, `node_modules`, etc. (se crea automáticamente si no existe).
- **Soporte opcional de `.gitignore`:** Si `pathspec` está instalado, los patrones de `.gitignore` también se respetan.
- **Versionado automático:** Los archivos de salida se numeran secuencialmente (`context_001.md`, `context_002.json`, etc.) dentro de `output/context/<cwd_safe>/`, evitando sobrescrituras.
- **Estadísticas detalladas:** Se genera un archivo JSON con el resumen de archivos procesados, líneas, tamaños y distribución por lenguaje.

**Ejemplo de salida (Markdown):**

```markdown
# CONTEXTO DEL PROYECTO

**Generado:** 2026-06-18 13:44:05  
**Sistema:** Linux-6.17.0 ...  
**Directorio:** /home/user/project  
**Extensiones:** .py, .md, .json

## Índice de archivos
- [context.py](#contextpy)
- [README.md](#READMEmd)
...

## Estructura de directorios
...
## Contenido de archivos
...
```

### `list_packages.py` – Listado de paquetes instalados

**Propósito:**  
Consulta múltiples gestores de paquetes del sistema (APT, Snap, Flatpak, Homebrew, Winget, Chocolatey, pip, npm, gem, etc.) y genera un informe completo en varios formatos (MD, JSON, XML, TXT o estadísticas). Soporta Linux, macOS y Windows, y permite seleccionar interactivamente los gestores a consultar.

**Uso:**

```bash
python3 list_packages.py
```

**Modo interactivo:**  
Pregunta qué gestores incluir, formato de salida, nombre base y si se desea ejecución en paralelo. Guarda perfiles para reutilizar la selección.

**Modo línea de comandos:**

```bash
python3 list_packages.py --format json --output mis_paquetes --quiet --include-manager pip npm
```

**Gestores soportados (por sistema):**

| Sistema | Gestores |
|---------|----------|
| Linux   | APT, PPAs, Snap, Flatpak, Pacman, DNF, YUM, Zypper, RPM, AppImage, GNU Stow |
| macOS   | Homebrew, MacPorts, pkgutil, Mac App Store (mas), LaunchAgents, system_profiler |
| Windows | winget, Chocolatey, Scoop, Registro Windows, WSL, Extensiones VS Code, Módulos PowerShell, Características Windows |
| Multi   | asdf, Nix, Guix, pip, npm, gem, cargo |

**Decisiones de implementación:**

- Cada gestor se implementa como una función independiente que devuelve una cadena con la lista de paquetes o `None` si no está disponible.
- La ejecución en paralelo (`ThreadPoolExecutor`) acelera la consulta cuando hay muchos gestores.
- Los resultados se almacenan en caché de perfil para reutilización.

### `rename.py` – Renombrador interactivo de archivos

**Propósito:**  
Renombra archivos de forma controlada con un asistente paso a paso. Normaliza los nombres: convierte a minúsculas (`casefold`), reemplaza espacios por un carácter configurable y opcionalmente elimina acentos (normalización Unicode a ASCII). Resuelve colisiones (archivos con el mismo nombre) añadiendo sufijos numéricos y tiene en cuenta sistemas de archivos **case‑insensitive** (como Windows o macOS). Incluye un comando `--undo` para deshacer la última operación.

**Uso:**

```bash
python3 rename.py                 # modo interactivo
python3 rename.py --undo          # deshacer último renombrado
```

**Flujo interactivo:**  

- Carga perfil anterior si existe.
- Pide directorio, carácter de reemplazo, normalización Unicode, seguir enlaces simbólicos, patrones de exclusión, modo simulación y límite de intentos para colisiones.
- Muestra una vista previa con los nombres originales y los nuevos.
- Confirma antes de ejecutar.

**Características técnicas:**

- **Detección de sistemas case‑insensitive:** La función `resolver_colisiones` verifica si el sistema trata mayúsculas y minúsculas como iguales, y evita colisiones incluso en esos casos.
- **Log de renombrados:** Guarda un registro en `output/rename/<cwd_safe>/.rename_history.json` con el mapeo origen‑destino, lo que permite el `--undo`.
- **Exclusión del propio script:** El script se excluye automáticamente para evitar renombrarse a sí mismo.

### `sort.py` – Ordenador con índice numérico

**Propósito:**  
Ordena archivos según diferentes criterios (nombre, tamaño, fecha de modificación, fecha de creación, longitud del nombre) y los renombra añadiendo un prefijo numérico. Ofrece control total sobre el formato del nuevo nombre (posición del índice, separador, número de dígitos, prefijo). Puede actuar sobre archivos específicos o sobre todo un directorio (con recursividad y filtros). Incluye modo deshacer.

**Uso:**

```bash
python3 sort.py --sort-by size --order desc --dry-run
python3 sort.py --wizard                 # asistente interactivo
python3 sort.py --undo
```

**Opciones principales:**

- `-s, --sort-by`: `name`, `size`, `mtime`, `ctime`, `namelength`.
- `-o, --order`: `asc` o `desc`.
- `-t, --tie-breaker`: criterios de desempate (múltiples).
- `--prefix`, `--sep`, `--digits`, `--index-after`: personalización del nombre.
- `-n, --dry-run`: simulación.
- Respeta `.sortignore` y `.gitignore` (si `pathspec` está instalado).

**Implementación:**

- La clave de ordenación se construye dinámicamente con una tupla que combina el criterio principal y los desempates.
- Se usa `fnmatch` y `pathspec` para los filtros.
- El log de renombrados se guarda en `output/sort/<cwd_safe>/.rename_log.json`.

### `classify.py` – Clasificador automático por tipo

**Propósito:**  
Organiza archivos en carpetas según su tipo (extensión) siguiendo reglas flexibles. Soporta filtros avanzados (fecha, tamaño, nombre), jerarquía de categorías (ej. `Imagenes/Fotos`), manejo de conflictos configurable (sobrescribir, renombrar, omitir, preguntar), modo espejo (mover a una carpeta con la misma estructura) y sincronización incremental. Además, permite descargar reglas desde una URL.

**Uso básico:**

```bash
python3 classify.py
```

El asistente interactivo guía en la configuración:

- Directorio, recursividad, archivos ocultos, enlaces simbólicos.
- Filtros de nombre (glob y regex), tamaño y fechas.
- Origen de las reglas (por defecto, archivo `.classify_rules.json`, o URL).
- Carpeta de destino (si se especifica, todos los archivos van a esa carpeta, sin clasificación por tipo).
- Preservación de estructura (cuando es recursivo).
- Manejo de conflictos.
- Modo simulación y generación de informes (CSV, HTML, JSON).

**Reglas:**  
El archivo de reglas es un JSON que asigna extensiones (clave) a categorías (valor). También admite patrones glob (ej. `"*.log"`: `"Logs"`). Si no se proporciona, se usa un conjunto por defecto que cubre imágenes, documentos, audio, video, código, comprimidos y ejecutables.

**Características avanzadas:**

- **Log histórico:** Cada ejecución guarda un JSON con los cambios realizados, permitiendo deshacer una operación específica (no solo la última) mediante `--undo <log_id>`.
- **Informes:** Genera resúmenes en CSV, HTML o JSON.
- **Papelera:** Si `send2trash` está instalado, los archivos pueden moverse a la papelera en lugar de borrarse.

### `compress_to_path.py` – Compresor/descompresor inteligente

**Propósito:**  
Comprime archivos y directorios en ZIP, TAR.GZ o 7z con un asistente interactivo que permite filtrar por extensión, tamaño, fecha, incluir/excluir patrones, y manejar archivos ya comprimidos de forma inteligente. Además, **procesa archivos comprimidos existentes** moviéndolos al directorio de salida si ya están en el formato destino, o convirtiéndolos al formato elegido (extrayendo y re-comprimiendo).

**Uso:**

```bash
python3 compress_to_path.py
```

El asistente pregunta:

- Modo compresión o restauración.
- Formato destino (ZIP, TAR.GZ, 7z).
- Contraseña (para ZIP y 7z, usando `pyzipper` para cifrado AES).
- División en volúmenes (ZIP).
- Exclusiones de extensiones.
- Filtros avanzados (tamaño, fecha, patrones).
- Compresión de subdirectorios como archivos individuales.
- Procesamiento de archivos comprimidos existentes (mover o convertir).
- Mover originales a la papelera tras comprimir con éxito.
- Preservación de metadatos Unix (permisos, propietario) en un archivo JSON.

**Decisiones de diseño:**

- **Detección de formatos ya comprimidos:** Se omite por defecto la compresión de archivos con extensiones como `.jpg`, `.mp3`, `.zip`, etc., para evitar re‑comprimir sin beneficio.
- **Conversión de archivos comprimidos:** Si se encuentra un `.zip` y se quiere comprimir a `.7z`, el script extrae temporalmente el contenido y lo vuelve a comprimir en el nuevo formato.
- **Paralelismo:** La compresión de múltiples archivos se puede ejecutar en paralelo usando `ThreadPoolExecutor`, con barra de progreso opcional.
- **Logs:** Guarda registro detallado de todas las operaciones.

### `http_server.py` – Servidor HTTP con interfaz web

**Propósito:**  
Levanta un servidor HTTP en el puerto 8080 que sirve el directorio actual con una interfaz web moderna, responsiva, con vista en miniaturas o detalles, descarga de archivos individuales o carpetas completas (como ZIP) y **vista previa** de imágenes, texto, audio, video y PDF. La preferencia de vista se guarda en `localStorage`.

**Uso:**

```bash
python3 http_server.py
```

Luego abre `http://localhost:8080` en el navegador.

**Características técnicas:**

- **Generación dinámica de HTML:** La plantilla incluye los datos del directorio (JSON) y se reemplaza en el servidor.
- **Seguridad básica:** Las rutas se resuelven con `secure_path` para evitar ataques de path traversal.
- **Descarga de carpetas:** Se crea un ZIP en memoria con `zipfile` y se envía al cliente.
- **Vista previa:** Usa `fetch` para obtener el archivo y, según el MIME type, lo muestra como imagen, video, audio, texto o PDF (iframe). Los archivos de texto se muestran escapados para evitar XSS.
- **Logging:** Registra las peticiones en `output/http_server/<cwd_safe>/http_server.log`.

### `file_sharing_server.py` – Servidor con subida de archivos

**Propósito:**  
Similar a `http_server.py`, pero añade la posibilidad de **subir archivos** desde el navegador. Permite compartir archivos en ambos sentidos, ideal para equipos en la misma red.

**Uso:**

```bash
python3 file_sharing_server.py
```

**Diferencias con `http_server.py`:**

- Incluye un formulario de subida en la interfaz.
- Maneja peticiones `POST` a `/upload` con `multipart/form-data`.
- Utiliza `cgi.FieldStorage` para procesar los archivos subidos (con límite de 1 GB configurable).
- Los archivos se guardan en el directorio raíz del servidor, evitando sobrescrituras añadiendo sufijos si es necesario.

### `git_diff_context.py` – Generador de diferencias Git

**Propósito:**  
Analiza el estado de un repositorio Git comparando el working directory con el HEAD, e incluye archivos **nuevos (untracked)**, modificados, eliminados y renombrados. Genera un informe detallado en múltiples formatos (MD, JSON, XML, TXT, HTML, patch) mostrando el contenido completo o el diff unificado. Soporta filtros por estado, extensión, patrones de exclusión, y muestra fechas de modificación locales y en HEAD.

**Uso:**

```bash
python3 git_diff_context.py
```

**Modo interactivo:**  
Pregunta qué estados incluir (`M`, `A`, `D`, `U`, `R`), extensiones, patrón de exclusión, estilo de diff (completo, unificado o ambos), formato de salida, compactación, números de línea, y si mostrar fechas.

**Características clave:**

- **Untracked con `-uall`:** Usa `git status --porcelain -uall` para listar todos los archivos no rastreados, incluso dentro de directorios no rastreados.
- **Contenido original:** Recupera el contenido del archivo en HEAD con `git show`.
- **Diff artificial para untracked:** Genera un diff comparando con `/dev/null`.
- **Ordenación por fecha:** Puede ordenar los archivos por fecha de modificación local (más reciente primero).
- **Soporte de `.contextignore`:** Filtra archivos que coincidan con los patrones.
- **Resaltado de sintaxis:** Si `pygments` está instalado, la salida HTML incluye resaltado.
- **Portapapeles:** Opción para copiar el contenido del primer archivo generado al portapapeles (requiere `pyperclip`).

---

## Arquitectura y decisiones de diseño

El proyecto sigue un conjunto de principios comunes que garantizan coherencia, mantenibilidad y facilidad de uso.

### Gestión de rutas con `path_manager.py`

Todos los scripts importan `path_manager.py` para resolver rutas de forma consistente. Esto centraliza la lógica de almacenamiento de logs, perfiles, caché y archivos de salida.

**Estructura:**

```
<repo_root>/
└── output/
    ├── context/
    │   ├── global/
    │   │   └── .contextignore
    │   └── <cwd_safe>/
    │       ├── context_001.md
    │       ├── context_001.json
    │       ├── context_stats_001.json
    │       └── cache/
    ├── list_packages/
    │   └── <cwd_safe>/
    │       ├── packages.md
    │       └── pkg_list.log
    ├── rename/
    │   └── <cwd_safe>/
    │       └── .rename_history.json
    ├── sort/
    │   └── <cwd_safe>/
    │       └── .rename_log.json
    ├── compress_to_path/
    │   └── <cwd_safe>/
    │       ├── compresor.log
    │       └── .compress_profile.json
    ├── http_server/
    │   └── <cwd_safe>/
    │       └── http_server.log
    └── ... (similar para cada script)
```

**`cwd_safe`** es una versión segura del directorio de trabajo actual (reemplaza separadores y dos puntos). Esto permite que cada script guarde sus archivos en una carpeta exclusiva para esa ruta, evitando colisiones cuando se ejecuta desde distintos proyectos.

**Perfiles globales:** Algunos scripts (como `context.py`) guardan perfiles en `output/<script>/global/` para que la configuración se comparta entre todas las ejecuciones desde cualquier directorio.

### Sistema de perfiles y persistencia

Cada herramienta puede guardar la configuración elegida en un archivo JSON (ej. `.context_profile.json`, `.rename_profile.json`). Al iniciar, se pregunta al usuario si desea cargar el perfil anterior, lo que acelera la configuración en usos repetidos.

Los perfiles pueden ser **locales** (en `output/<script>/<cwd_safe>/`) o **globales** (en `output/<script>/global/`), según la naturaleza de la configuración. Por ejemplo, el perfil de `context.py` es global porque las preferencias de extensiones y formato suelen ser personales, mientras que el perfil de `compress_to_path.py` puede ser local porque depende del directorio.

### Logging y trazabilidad

Todos los scripts implementan logging con dos salidas:

- **Archivo de log** (en `output/<script>/<cwd_safe>/<script>.log`) con nivel `DEBUG`, que registra todos los eventos, errores y advertencias.
- **Consola** con nivel `INFO` o `WARNING` según el modo (silencioso o no).

Esto facilita la depuración y el seguimiento de operaciones, especialmente cuando se trabaja con muchos archivos o en modo batch.

### Manejo de codificaciones y archivos binarios

Dado que los scripts procesan archivos de texto de diversos orígenes, se ha implementado una estrategia robusta:

1. **Detección automática** con `charset-normalizer` (si está instalado).
2. **Caché de codificaciones** para no repetir la detección en el mismo archivo.
3. **Fallback** a una lista de codificaciones comunes (`utf-8`, `latin-1`, `cp1252`, etc.).
4. **Detección de binarios** leyendo los primeros bytes y buscando el byte nulo (`\0`).

Esta estrategia se utiliza en `context.py` y `git_diff_context.py` para leer archivos de texto, y en `compress_to_path.py` para decidir si un archivo es comprimible o no.

### Concurrencia y rendimiento

Varios scripts (`list_packages.py`, `context.py`, `compress_to_path.py`, `git_diff_context.py`) aprovechan `ThreadPoolExecutor` para ejecutar tareas en paralelo:

- **Lectura de archivos** en `context.py` y `git_diff_context.py` (lectura de contenido).
- **Consulta de gestores** en `list_packages.py`.
- **Compresión de archivos** en `compress_to_path.py`.

Esto reduce significativamente el tiempo de ejecución cuando hay muchos elementos. Se utiliza un número de workers configurable (por defecto 8) y se integra con `tqdm` para mostrar el progreso.

### Formatos de salida y extensibilidad

La mayoría de las herramientas soportan múltiples formatos de salida (Markdown, JSON, XML, TXT, etc.). La lógica de generación está separada en funciones específicas (`write_output_md`, `write_output_json`, etc.), lo que facilita añadir nuevos formatos en el futuro.

En `context.py`, además, se puede generar **todos los formatos a la vez** con la opción `all`, numerando automáticamente los archivos.

### Integración con `.gitignore` y `.contextignore`

- **`.contextignore`** es un archivo específico del proyecto (similar a `.gitignore`) que contiene patrones de archivos/directorios a ignorar por `context.py` y `git_diff_context.py`. Se crea automáticamente con los directorios por defecto (`__pycache__`, `node_modules`, etc.) si no existe.
- **`.gitignore`** se respeta opcionalmente en `context.py`, `sort.py` y `git_diff_context.py` si la librería `pathspec` está instalada. Esto evita incluir archivos que Git ya ignora.

La función `should_ignore` combina ambos sistemas y maneja patrones con `/` para directorios.

### Modo deshacer (undo)

Varias herramientas (`rename.py`, `sort.py`, `classify.py`, `compress_to_path.py` en cierta medida) implementan un mecanismo de **deshacer** basado en logs JSON. Cada operación de renombrado/movimiento registra el mapeo origen‑destino con una marca de tiempo. El comando `--undo` lee el log más reciente (o uno específico) y revierte los cambios.

Esto proporciona una red de seguridad ante errores, permitiendo al usuario recuperar el estado anterior sin tener que hacer copias de seguridad manuales.

---

## Licencia

MIT. Siéntete libre de usar, modificar y distribuir estos scripts. Se agradece la atribución, pero no es obligatoria.

---

**¡Disfruta de estas herramientas y optimiza tu flujo de trabajo!**
