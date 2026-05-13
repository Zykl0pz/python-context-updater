#!/usr/bin/env python3
"""
Script que comprime cada archivo individual del directorio actual en archivos ZIP separados.
Los archivos comprimidos se guardan dentro de una carpeta llamada "comprimidos".
Los archivos originales no se modifican.
"""

import os
import zipfile
from pathlib import Path

def main():
    # Directorio actual desde donde se ejecuta el script
    directorio_actual = Path.cwd()
    
    # Nombre de la carpeta donde se guardarán los ZIP
    carpeta_destino = directorio_actual / "comprimidos"
    
    # Crear la carpeta si no existe
    carpeta_destino.mkdir(exist_ok=True)
    print(f"Usando carpeta de destino: {carpeta_destino}")

    # Obtener el nombre del script para no comprimirlo a sí mismo
    script_nombre = Path(__file__).name

    # Recorrer todos los elementos en el directorio actual
    for entrada in directorio_actual.iterdir():
        # Solo procesamos archivos (no directorios)
        if entrada.is_file():
            # Ignorar el propio script y cualquier archivo ZIP para evitar reprocesamiento accidental
            if entrada.name == script_nombre or entrada.suffix.lower() == '.zip':
                print(f"Saltando: {entrada.name}")
                continue

            # Nombre del archivo ZIP de salida (mismo nombre base + .zip)
            nombre_zip = entrada.stem + ".zip"
            ruta_zip = carpeta_destino / nombre_zip

            try:
                print(f"Comprimiendo '{entrada.name}' -> '{ruta_zip}'...")
                with zipfile.ZipFile(ruta_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
                    # Agregar el archivo al ZIP usando solo su nombre (sin ruta)
                    zf.write(entrada, arcname=entrada.name)
                print(f"  OK: {ruta_zip}")
            except Exception as e:
                print(f"  ERROR al comprimir '{entrada.name}': {e}")

    print("\nProceso completado. Los archivos comprimidos están en:", carpeta_destino)

if __name__ == "__main__":
    main()