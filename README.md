# Conjunto de Herramientas para Desarrolladores

Este repositorio contiene varios scripts independientes que facilitan tareas comunes en el día a día de un programador: generar documentación de contexto de un proyecto, listar paquetes instalados en el sistema, renombrar archivos de forma interactiva, ordenar y renombrar con índices, comprimir/descomprimir archivos y levantar un servidor HTTP con interfaz gráfica.

Todos los scripts están escritos en Python 3 y funcionan en Linux, macOS y Windows (con algunas limitaciones en los gestores de paquetes).

---

## Requisitos

- **Python 3.7 o superior**.
- Dependencias opcionales (según el script):
  - `tqdm` – barras de progreso.
  - `charset-normalizer` – detección precisa de codificaciones.
  - `pathspec` – soporte para `.gitignore`.
  - `py7zr` – soporte para formato 7z.
  - `pyzipper` – compresión ZIP con contraseña.
  - `send2trash` – mover archivos a la papelera.
  - `PyPDF2` o `pdfplumber` – extracción de texto de PDF.

Instálalas con `pip` cuando el script lo requiera.

---

## Instalación

1. **Clona o descarga** este repositorio en tu equipo.
2. (Opcional) Agrega la carpeta a tu `PATH` o crea alias para ejecutar los scripts desde cualquier directorio (ver sección “Comandos globales” al final de cada script o los ejemplos en el README original).

Los scripts no requieren instalación adicional; se ejecutan directamente con Python.

```bash
python3 contexto.py   # ejemplo
```

---

## Scripts disponibles

### 1. `context.py` – Generador de contexto de código

Analiza el directorio actual, muestra un árbol de archivos y extrae el contenido de aquellos con extensiones seleccionadas, generando un documento de contexto (Markdown, JSON, XML, TXT o solo estadísticas). Ideal para alimentar modelos de lenguaje o documentar rápidamente la estructura de un proyecto.

**Uso básico:**

```bash
python3 context.py
```

Sigue el asistente interactivo para elegir extensiones, filtros, formato y modo compacto.

**Características:**

- Respeta `.contextignore` (se crea automáticamente con directorios ignorados por defecto).
- Opcionalmente respeta `.gitignore` (requiere `pathspec`).
- Detecta la codificación de archivos de texto.
- Extrae texto de PDF, DOCX, XLSX, ODT, etc. (si las librerías están instaladas).
- Genera árbol de directorios con tamaños.

**Perfiles:** Guarda la configuración en `.context_profile.json`.

---

### 2. `list_packages.py` – Listado de paquetes instalados

Consulta múltiples gestores de paquetes (APT, Snap, Flatpak, Homebrew, Winget, pip, npm, etc.) y produce una lista completa en formato Markdown, JSON, XML, TXT o solo estadísticas. Soporta Linux, macOS y Windows.

**Uso básico:**

```bash
python3 list_packages.py
```

Por defecto inicia un modo interactivo donde seleccionas qué gestores consultar y el formato de salida.

**Opciones de línea de comandos:**

```bash
python3 list_packages.py --format json --output mis_paquetes --quiet
```

**Gestores soportados:** APT, DNF, Pacman, Zypper, Snap, Flatpak, Homebrew, MacPorts, winget, Chocolatey, Scoop, pip, npm, gem, cargo, asdf, Nix, etc.

**Salida:** genera archivos como `packages.md`, `packages.json`, etc., y un log `pkg_list.log`.

---

### 3. `rename.py` – Renombrador interactivo de archivos

Permite renombrar archivos de forma interactiva con un menú paso a paso. Normaliza nombres (minúsculas, espacios por guión bajo, eliminación de acentos opcional) y resuelve colisiones añadiendo sufijos numéricos. Incluye modo `--undo` para deshacer el último renombrado.

**Uso:**

```bash
python3 rename.py               # modo interactivo
python3 rename.py --undo        # deshace el último renombrado
```

**Configuración interactiva:**

- Directorio a procesar.
- Carácter de reemplazo para espacios (por defecto `_`).
- Normalización Unicode (convertir acentos a ASCII).
- Seguir enlaces simbólicos.
- Patrones de exclusión (ej. `*.tmp`).
- Modo simulación (dry-run).
- Guardar perfil de configuración.

**Perfil:** se guarda en `.rename_profile.json`.

---

### 4. `sort.py` – Ordena y renombra archivos con índice numérico

Ordena archivos según criterios (nombre, tamaño, fecha, longitud del nombre) y los renombra añadiendo un prefijo numérico. Permite control total sobre el formato del nombre. También incluye deshacer.

**Ejemplos:**

```bash
python3 sort.py --sort-by size --order desc --dry-run
python3 sort.py --wizard                # asistente interactivo
python3 sort.py --undo
```

**Opciones destacadas:**

- `-s`, `--sort-by`: criterio principal (`name`, `size`, `mtime`, `ctime`, `namelength`).
- `-o`, `--order`: `asc` o `desc`.
- `-t`, `--tie-breaker`: criterios de desempate.
- `--prefix`, `--sep`, `--digits`, `--index-after`: personalización del nombre.
- `-n`, `--dry-run`: solo simular.
- Respeta `.sortignore` y `.gitignore`.

---

### 5. `compress_to_path.py` – Compresor/descompresor interactivo

Comprime archivos y directorios en ZIP, TAR.GZ o 7z. Permite filtrar por extensión, tamaño, fecha, y mover los originales a la papelera. Además, **procesa archivos ya comprimidos** existentes: si están en el formato destino, los mueve a la carpeta de salida; si están en otro formato soportado, los convierte al formato elegido.

**Uso:**

```bash
python3 compress_to_path.py
```

El asistente pregunta:

- Modo compresión o restauración.
- Formato destino.
- Contraseña (para ZIP y 7z).
- División en volúmenes (ZIP).
- Exclusiones de extensiones.
- Filtros avanzados (tamaño, fecha, patrones).
- Compresión de subdirectorios como archivos individuales.
- Procesamiento de archivos comprimidos existentes.

**Perfil:** guarda la configuración en `.compress_profile.json`.

---

### 6. `http_server.py` – Servidor HTTP con interfaz web

Levanta un servidor HTTP en el puerto 8080 que sirve el directorio actual. La interfaz web muestra archivos y carpetas en modo “miniaturas” o “detalles”, permite descargar archivos o carpetas completas (como ZIP) y ofrece **vista previa** de imágenes, texto, audio, video y PDF.

**Uso:**

```bash
python3 http_server.py
```

Luego abre `http://localhost:8080` en tu navegador.

**Características:**

- Navegación por directorios.
- Descarga de archivos individuales.
- Descarga de carpetas completas como ZIP.
- Vista previa integrada.
- Persistencia de la vista elegida (localStorage).
- Compatible con móviles (diseño responsivo).

---

## Configuración y perfiles

Muchos scripts guardan un perfil JSON (por ejemplo, `.context_profile.json`, `.rename_profile.json`, `.compress_profile.json`, `.sort_profile.json`) con la última configuración utilizada. En ejecuciones posteriores se pregunta si se desea cargar ese perfil, lo que agiliza el proceso.

Además, los scripts pueden leer archivos de exclusión:

- `.contextignore` – patrones de archivos/carpetas a ignorar por `context.py`.
- `.sortignore` – similar para `sort.py`.
- `.gitignore` – opcionalmente respetado (si `pathspec` está instalado).

---

## Comandos globales (opcional)

Puedes crear alias para ejecutar cualquier script desde cualquier carpeta sin escribir `python3 ruta/completa/script.py`.

### Linux / macOS

Añade al `~/.bashrc` o `~/.zshrc`:

```bash
alias getcontext='python3 /ruta/a/context.py'
alias listpkgs='python3 /ruta/a/list_packages.py'
alias renames='python3 /ruta/a/rename.py'
alias comprimir='python3 /ruta/a/compress_to_path.py'
alias servidor='python3 /ruta/a/http_server.py'
alias ordenar='python3 /ruta/a/sort.py'
```

Luego recarga: `source ~/.bashrc`.

### Windows

Crea archivos `.bat` en una carpeta del `PATH` con contenido como:

```batch
@echo off
python C:\ruta\context.py %*
```

---

## Licencia

MIT. Siéntete libre de usar, modificar y distribuir estos scripts.

---

## Notas finales

- Los scripts están diseñados para ser **independientes**; cada uno puede usarse por separado.
- Algunas funcionalidades (como la extracción de texto de PDF o el manejo de 7z) requieren librerías adicionales que se indican en tiempo de ejecución.
- Para problemas o sugerencias, revisa los logs generados (`context.log`, `pkg_list.log`, etc.).

¡Disfruta de estas herramientas y optimiza tu flujo de trabajo!
