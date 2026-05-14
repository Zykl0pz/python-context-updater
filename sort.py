#!/usr/bin/env python3
"""
Script para ordenar y renombrar los archivos del directorio actual,
anteponiendo un índice numérico de 3 cifras.
"""

import os
from pathlib import Path
from datetime import datetime


def obtener_archivos():
    """Devuelve lista de archivos (solo archivos regulares) en el directorio actual."""
    ruta = Path.cwd()
    archivos = [p for p in ruta.iterdir() if p.is_file()]
    return archivos


def mostrar_menu_orden():
    """Muestra menú de criterios de orden y devuelve la opción elegida."""
    print("\nSeleccione el criterio de ordenamiento:")
    print("1. Fecha de modificación")
    print("2. Fecha de creación (ctime)")
    print("3. Orden alfabético (nombre)")
    print("4. Largo del nombre")
    print("5. Tamaño")
    print("0. Salir")
    opcion = input("Opción: ").strip()
    return opcion


def elegir_direccion():
    """Pregunta si orden ascendente o descendente."""
    print("\nSeleccione el orden:")
    print("1. Ascendente (menor a mayor / A-Z)")
    print("2. Descendente (mayor a menor / Z-A)")
    direccion = input("Opción: ").strip()
    return direccion


def ordenar_archivos(archivos, criterio, ascendente):
    """
    Ordena la lista de archivos según el criterio y dirección.
    criterio: una de las claves 'mtime', 'ctime', 'nombre', 'largo', 'tamano'
    """
    if criterio == "mtime":
        clave = lambda p: p.stat().st_mtime
    elif criterio == "ctime":
        clave = lambda p: p.stat().st_ctime
    elif criterio == "nombre":
        clave = lambda p: p.name.lower()  # insensible a mayúsculas
    elif criterio == "largo":
        clave = lambda p: len(p.name)
    elif criterio == "tamano":
        clave = lambda p: p.stat().st_size
    else:
        raise ValueError("Criterio no válido")

    archivos_ordenados = sorted(archivos, key=clave, reverse=not ascendente)
    return archivos_ordenados


def mostrar_lista(archivos, mensaje):
    """Imprime la lista de archivos con su nombre actual."""
    print(f"\n{mensaje} ({len(archivos)} archivos):")
    for i, archivo in enumerate(archivos, start=1):
        print(f"{i:3d}. {archivo.name}")


def confirmar(mensaje):
    """Pregunta s/n y devuelve True si responde 's' o 'si'."""
    resp = input(f"{mensaje} (s/n): ").strip().lower()
    return resp in ("s", "si", "sí")


def renombrar_con_indices(archivos_ordenados):
    """
    Renombra los archivos anteponiendo índice de 3 dígitos.
    Verifica conflictos y pide confirmación si existen.
    """
    # Construir mapeo: ruta_actual -> ruta_nueva
    mapeo = []
    conflictos = []
    for i, archivo in enumerate(archivos_ordenados):
        nuevo_nombre = f"{i:03d}_{archivo.name}"
        nueva_ruta = archivo.with_name(nuevo_nombre)
        mapeo.append((archivo, nueva_ruta))
        if nueva_ruta.exists() and nueva_ruta != archivo:
            conflictos.append((archivo, nueva_ruta))

    # Si hay conflictos, mostrar y preguntar
    if conflictos:
        print("\n¡ATENCIÓN! Los siguientes destinos ya existen:")
        for orig, dest in conflictos:
            print(f"  {orig.name}  ->  {dest.name}")
        if not confirmar("¿Sobrescribir los archivos existentes?"):
            print("Operación cancelada.")
            return False

    # Proceder al renombrado
    for orig, dest in mapeo:
        try:
            orig.replace(dest)  # replace sobreescribe si existe
            print(f"Renombrado: {orig.name} -> {dest.name}")
        except Exception as e:
            print(f"Error al renombrar {orig.name}: {e}")
    return True


def main():
    print("=== Ordenador de archivos con índice numérico ===")

    archivos = obtener_archivos()
    if not archivos:
        print("No se encontraron archivos en el directorio actual.")
        return

    print(f"Se encontraron {len(archivos)} archivos.")

    # Elegir criterio
    while True:
        opcion = mostrar_menu_orden()
        if opcion == "0":
            print("Saliendo.")
            return
        elif opcion in ("1","2","3","4","5"):
            break
        else:
            print("Opción no válida, intente de nuevo.")

    criterios = {
        "1": "mtime",
        "2": "ctime",
        "3": "nombre",
        "4": "largo",
        "5": "tamano"
    }
    criterio = criterios[opcion]

    # Elegir dirección
    while True:
        dir_opcion = elegir_direccion()
        if dir_opcion in ("1","2"):
            break
        else:
            print("Opción no válida, intente de nuevo.")
    ascendente = (dir_opcion == "1")

    # Ordenar
    archivos_ordenados = ordenar_archivos(archivos, criterio, ascendente)

    # Mostrar resultado ordenado
    nombre_criterio = {
        "mtime": "fecha de modificación",
        "ctime": "fecha de creación (ctime)",
        "nombre": "nombre alfabético",
        "largo": "largo del nombre",
        "tamano": "tamaño"
    }
    direccion_str = "ascendente" if ascendente else "descendente"
    mostrar_lista(archivos_ordenados,
                  f"Archivos ordenados por {nombre_criterio[criterio]} ({direccion_str})")

    # Confirmar renombrado
    if not confirmar("¿Desea renombrar estos archivos con los índices mostrados?"):
        print("Operación cancelada.")
        return

    # Ejecutar renombrado
    exito = renombrar_con_indices(archivos_ordenados)
    if exito:
        print("Renombrado completado exitosamente.")
    else:
        print("El renombrado no se completó (cancelado o con errores).")


if __name__ == "__main__":
    main()