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
