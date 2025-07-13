# Documentación de `context.py`

## Índice
- [Introducción](#introducción)
- [Instalación](#instalación)
- [Guía de Uso](#guía-de-uso)
  - [Primeros Pasos](#primeros-pasos)
- [Funcionalidades](#funcionalidades)
  - [Mapa de Extensiones a Lenguajes de Programación](#mapa-de-extensiones-a-lenguajes-de-programación)
  - [Funciones Principales](#funciones-principales)
- [Conclusión](#conclusión)

## Introducción
El archivo `context.py` es un script en Python que permite mapear extensiones de archivos a sus respectivos lenguajes de programación. Además, genera un archivo de texto que contiene la estructura de directorios y el contenido de los archivos en el directorio actual.

## Instalación
Para instalar y utilizar `context.py`, sigue estos pasos:

1. **Clonar el repositorio**:
   ```bash
   git clone https://github.com/Fant324/Agencia-Empleadora-DPOO.git
   cd Agencia-Empleadora-DPOO/src
   ```

2. **Instalar Python**:
   Asegúrate de tener Python instalado en tu sistema. Puedes descargarlo desde [python.org](https://www.python.org/downloads/).

3. **Ejecutar el script**:
   Una vez que estés en el directorio donde se encuentra `context.py`, puedes ejecutarlo con el siguiente comando:
   ```bash
   python context.py
   ```

## Para usarlo con el comando getContext desde terminal en el directorio que estés(opcional):
1. Abre tu archivo `~/.bashrc` en un editor de texto. Puedes usar `nano`, `vim`, o cualquier otro editor que prefieras. Por ejemplo, usando `nano`:

   ```bash
   nano ~/.bashrc
   ```

2. Agrega la siguiente línea al final del archivo:

   ```bash
   alias getContext='python3 $(find . -name "context.py" -print -quit)'
   ```

   Aquí, `find . -name "context.py" -print -quit` busca el archivo `context.py` en el directorio actual y sus subdirectorios. El uso de `-print -quit` asegura que solo se imprima la primera coincidencia y se detenga la búsqueda.

3. Guarda los cambios y cierra el editor. Si usaste `nano`, puedes hacerlo presionando `CTRL + X`, luego `Y` para confirmar los cambios, y `Enter` para salir.

4. Para que los cambios surtan efecto, recarga tu archivo `~/.bashrc` ejecutando:

   ```bash
   source ~/.bashrc
   ```

5. Ahora puedes usar el comando `getContext` en cualquier directorio. Si hay un archivo `context.py` en el directorio actual o en sus subdirectorios, se ejecutará.

Ten en cuenta que este alias asume que tienes Python 3 instalado y que el archivo `context.py` es ejecutable con Python. Si necesitas usar una versión diferente de Python, simplemente reemplaza `python3` con el comando correspondiente.

## Guía de Uso

### Primeros Pasos
1. **Estructura de Archivos**:
   Asegúrate de que el directorio donde ejecutas el script contenga archivos con diferentes extensiones para que el script pueda mapearlos correctamente.

2. **Ejecutar el Script**:
   Al ejecutar el script, se generará un archivo llamado `context.txt` en el mismo directorio. Este archivo contendrá la lista de archivos y su respectivo lenguaje de programación.

## Funcionalidades

### Mapa de Extensiones a Lenguajes de Programación
El script contiene un diccionario llamado `language_map` que mapea las extensiones de archivo a sus lenguajes de programación correspondientes. Aquí hay algunos ejemplos:

- `.py` → Python
- `.js` → JavaScript
- `.html` → HTML
- `.java` → Java
- `.rb` → Ruby

### Funciones Principales
1. **`get_language(extension)`**:
   - **Descripción**: Esta función toma una extensión de archivo como argumento y devuelve el lenguaje de programación correspondiente utilizando el diccionario `language_map`.
   - **Uso**:
     ```python
     language = get_language('.py')  # Devuelve 'Python'
     ```

2. **`main()`**:
   - **Descripción**: Esta es la función principal que se ejecuta al iniciar el script. Recorre todos los archivos en el directorio actual, determina su extensión y escribe la información en `context.txt`.
   - **Uso**: No se llama directamente, se ejecuta automáticamente al correr el script.

## Conclusión
El script `context.py` es una herramienta útil para desarrolladores que desean mapear extensiones de archivos a lenguajes de programación y generar un informe de la estructura de archivos en un directorio. Asegúrate de tener Python instalado y sigue los pasos de instalación para comenzar a usarlo.
