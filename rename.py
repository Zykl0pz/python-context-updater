#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script para renombrar todos los archivos del directorio actual.
Formato: minúsculas y espacios reemplazados por '_'.
No requiere dependencias externas (solo Python estándar).
"""

import os
import sys

def main():
    # Obtener el directorio donde se ejecuta el script
    directorio_actual = os.getcwd()
    script_nombre = os.path.basename(__file__)

    print(f"Renombrando archivos en: {directorio_actual}")

    # Listar todos los elementos del directorio
    for nombre_archivo in os.listdir(directorio_actual):
        ruta_completa = os.path.join(directorio_actual, nombre_archivo)

        # Ignorar directorios y el propio script
        if not os.path.isfile(ruta_completa):
            continue
        if nombre_archivo == script_nombre:
            print(f"Saltando el propio script: {nombre_archivo}")
            continue

        # Generar el nuevo nombre: minúsculas + espacios -> '_'
        nuevo_nombre = nombre_archivo.lower().replace(' ', '_')

        # Si el nombre no cambió, no hacemos nada
        if nuevo_nombre == nombre_archivo:
            continue

        nueva_ruta = os.path.join(directorio_actual, nuevo_nombre)

        # Evitar colisiones: si ya existe un archivo con el nuevo nombre, añadir sufijo
        contador = 1
        nombre_base, extension = os.path.splitext(nuevo_nombre)
        while os.path.exists(nueva_ruta):
            nuevo_nombre_unico = f"{nombre_base}_{contador}{extension}"
            nueva_ruta = os.path.join(directorio_actual, nuevo_nombre_unico)
            contador += 1

        # Realizar el renombrado
        try:
            os.rename(ruta_completa, nueva_ruta)
            print(f"'{nombre_archivo}' -> '{os.path.basename(nueva_ruta)}'")
        except Exception as e:
            print(f"Error al renombrar '{nombre_archivo}': {e}", file=sys.stderr)

if __name__ == "__main__":
    main()