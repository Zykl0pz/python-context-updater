#!/usr/bin/env python3
"""
Ordena y renombra archivos con índice numérico (parametrizable vía CLI).
Uso:
    python ordenar_archivos.py --sort-by size --order desc --dry-run
"""

import os
import argparse
from pathlib import Path


def obtener_archivos(directorio):
    """Devuelve lista de archivos regulares en el directorio dado."""
    ruta = Path(directorio).resolve()
    if not ruta.is_dir():
        raise NotADirectoryError(f"El directorio '{directorio}' no existe o no es válido.")
    archivos = [p for p in ruta.iterdir() if p.is_file()]
    return archivos


def mostrar_menu_orden():
    """Menú interactivo para elegir criterio (solo se usa si no hay CLI)."""
    print("\nSeleccione el criterio de ordenamiento:")
    print("1. Fecha de modificación (mtime)")
    print("2. Fecha de creación (ctime)")
    print("3. Orden alfabético (nombre)")
    print("4. Largo del nombre")
    print("5. Tamaño")
    print("0. Salir")
    opcion = input("Opción: ").strip()
    return opcion


def elegir_direccion():
    """Menú interactivo para dirección (asc/desc)."""
    print("\nSeleccione el orden:")
    print("1. Ascendente (menor a mayor / A-Z)")
    print("2. Descendente (mayor a menor / Z-A)")
    direccion = input("Opción: ").strip()
    return direccion


def ordenar_archivos(archivos, criterio, ascendente):
    """
    Ordena la lista de archivos según criterio y dirección.
    criterio: 'mtime', 'ctime', 'name', 'namelength', 'size'
    """
    if criterio == "mtime":
        clave = lambda p: p.stat().st_mtime
    elif criterio == "ctime":
        clave = lambda p: p.stat().st_ctime
    elif criterio == "name":
        clave = lambda p: p.name.lower()
    elif criterio == "namelength":
        clave = lambda p: len(p.name)
    elif criterio == "size":
        clave = lambda p: p.stat().st_size
    else:
        raise ValueError("Criterio no válido")

    return sorted(archivos, key=clave, reverse=not ascendente)


def mostrar_lista(archivos, mensaje):
    """Imprime la lista numerada temporal."""
    print(f"\n{mensaje} ({len(archivos)} archivos):")
    for i, archivo in enumerate(archivos, start=1):
        print(f"{i:3d}. {archivo.name}")


def confirmar(mensaje):
    """Pregunta s/n. Si se está en modo no interactivo con --yes, devuelve True."""
    # Este flag se controla desde la lógica principal, aquí mantenemos la función por claridad.
    resp = input(f"{mensaje} (s/n): ").strip().lower()
    return resp in ("s", "si", "sí")


def renombrar_con_indices(archivos_ordenados):
    """Renombra los archivos anteponiendo índice de tres dígitos. Devuelve True si éxito."""
    mapeo = []
    conflictos = []
    for i, archivo in enumerate(archivos_ordenados):
        nuevo_nombre = f"{i:03d}_{archivo.name}"
        nueva_ruta = archivo.with_name(nuevo_nombre)
        mapeo.append((archivo, nueva_ruta))
        if nueva_ruta.exists() and nueva_ruta != archivo:
            conflictos.append((archivo, nueva_ruta))

    if conflictos:
        print("\n¡ATENCIÓN! Los siguientes destinos ya existen:")
        for orig, dest in conflictos:
            print(f"  {orig.name}  ->  {dest.name}")
        if not confirmar("¿Sobrescribir los archivos existentes?"):
            print("Operación cancelada.")
            return False

    for orig, dest in mapeo:
        try:
            orig.replace(dest)
            print(f"Renombrado: {orig.name} -> {dest.name}")
        except Exception as e:
            print(f"Error al renombrar {orig.name}: {e}")
    return True


def parse_args():
    parser = argparse.ArgumentParser(
        description="Ordena archivos y los renombra con prefijo numérico 000_, 001_, ..."
    )
    parser.add_argument("--path", "-p",
                        default=".",
                        help="Directorio donde se encuentran los archivos (por defecto: actual)")
    parser.add_argument("--sort-by", "-s",
                        choices=["mtime", "ctime", "name", "namelength", "size"],
                        help="Criterio de ordenamiento")
    parser.add_argument("--order", "-o",
                        choices=["asc", "desc"],
                        help="Dirección del orden (asc=ascendente, desc=descendente)")
    parser.add_argument("--dry-run", "-n",
                        action="store_true",
                        help="Solo muestra el orden sin renombrar")
    parser.add_argument("--yes", "-y",
                        action="store_true",
                        help="Omite confirmaciones (para scripts)")
    return parser.parse_args()


def interactive_mode(directorio):
    """Modo interactivo original."""
    archivos = obtener_archivos(directorio)
    if not archivos:
        print("No se encontraron archivos en el directorio actual.")
        return

    print(f"Se encontraron {len(archivos)} archivos.")

    while True:
        opcion = mostrar_menu_orden()
        if opcion == "0":
            print("Saliendo.")
            return
        elif opcion in ("1", "2", "3", "4", "5"):
            break
        else:
            print("Opción no válida, intente de nuevo.")

    criterios = {"1": "mtime", "2": "ctime", "3": "name", "4": "namelength", "5": "size"}
    criterio = criterios[opcion]

    while True:
        dir_opcion = elegir_direccion()
        if dir_opcion in ("1", "2"):
            break
        else:
            print("Opción no válida, intente de nuevo.")
    ascendente = (dir_opcion == "1")

    archivos_ordenados = ordenar_archivos(archivos, criterio, ascendente)

    nombre_criterio = {
        "mtime": "fecha de modificación",
        "ctime": "fecha de creación",
        "name": "nombre alfabético",
        "namelength": "largo del nombre",
        "size": "tamaño"
    }
    direccion_str = "ascendente" if ascendente else "descendente"
    mostrar_lista(archivos_ordenados,
                  f"Archivos ordenados por {nombre_criterio[criterio]} ({direccion_str})")

    if not confirmar("¿Desea renombrar estos archivos con los índices mostrados?"):
        print("Operación cancelada.")
        return

    exito = renombrar_con_indices(archivos_ordenados)
    if exito:
        print("Renombrado completado exitosamente.")
    else:
        print("El renombrado no se completó (cancelado o con errores).")


def main():
    args = parse_args()

    # Si se dieron argumentos de orden, se usa modo no interactivo.
    if args.sort_by or args.order or args.dry_run or args.yes:
        # Validar que se hayan dado ambos: sort_by y order (si no es solo dry-run con orden actual?)
        if not args.sort_by or not args.order:
            print("Error: en modo CLI debe especificar --sort-by y --order (o use modo interactivo sin argumentos).")
            return

        archivos = obtener_archivos(args.path)
        if not archivos:
            print("No se encontraron archivos en el directorio especificado.")
            return

        ascendente = (args.order == "asc")
        archivos_ordenados = ordenar_archivos(archivos, args.sort_by, ascendente)

        nombre_criterio = {
            "mtime": "fecha de modificación",
            "ctime": "fecha de creación",
            "name": "nombre",
            "namelength": "largo nombre",
            "size": "tamaño"
        }
        direccion_str = "ascendente" if ascendente else "descendente"
        mostrar_lista(archivos_ordenados,
                      f"Orden: {nombre_criterio[args.sort_by]} ({direccion_str})")

        if args.dry_run:
            print("Modo simulación: no se realizará ningún cambio.")
            return

        if not args.yes:
            if not confirmar("¿Proceder al renombrado?"):
                print("Operación cancelada.")
                return

        exito = renombrar_con_indices(archivos_ordenados)
        if exito:
            print("Renombrado completado exitosamente.")
        else:
            print("Falló el renombrado.")

    else:
        # Sin argumentos relevantes -> modo interactivo
        interactive_mode(args.path)


if __name__ == "__main__":
    main()