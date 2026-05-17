#!/usr/bin/env python3
"""
Script para listar todos los paquetes instalados en Ubuntu desde:
- APT (paquetes .deb)
- Snap
- Flatpak

Los resultados se guardan en 'pkgs.md' con formato Markdown.
"""

import subprocess
import sys
from pathlib import Path

# ---- Funciones auxiliares ----
def run_command(cmd):
    """Ejecuta un comando y devuelve su salida (texto). Si falla, devuelve None."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return None
    except Exception:
        return None

def command_exists(cmd):
    """Verifica si un comando está disponible en el sistema."""
    return run_command(f"which {cmd}") is not None

def write_section(f, title, content, is_table=False):
    """Escribe una sección formateada en el archivo Markdown."""
    f.write(f"## {title}\n\n")
    if content is None:
        f.write("⚠️ No se pudo obtener la lista o el gestor no está instalado.\n\n")
    elif not content.strip():
        f.write("✅ No hay paquetes instalados con este gestor.\n\n")
    else:
        if is_table:
            f.write(content)
        else:
            f.write("```\n")
            f.write(content)
            f.write("\n```\n")
        f.write("\n")

def get_apt_packages():
    """Lista paquetes APT (nombre y versión)."""
    if not command_exists("dpkg-query"):
        return None
    output = run_command("dpkg-query -W -f='${Package} ${Version}\\n'")
    if output:
        # Ordenar alfabéticamente
        lines = sorted(output.splitlines())
        return "\n".join(lines)
    return None

def get_snap_packages():
    """Lista paquetes Snap (nombre y versión)."""
    if not command_exists("snap"):
        return None
    output = run_command("snap list")
    if output:
        lines = output.splitlines()
        if len(lines) > 1:
            # Saltar cabecera (primera línea)
            data_lines = lines[1:]
            # Formato: Name  Version  Rev  Tracking  Publisher  Notes
            # Extraemos solo Name y Version
            packages = []
            for line in data_lines:
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0]
                    version = parts[1]
                    packages.append(f"{name} {version}")
            return "\n".join(sorted(packages))
    return None

def get_flatpak_packages():
    """Lista paquetes Flatpak (aplicaciones y runtimes, con nombre y versión)."""
    if not command_exists("flatpak"):
        return None
    # Incluye apps y runtimes; mostramos ID y versión
    output = run_command("flatpak list --columns=application,version")
    if output:
        lines = output.splitlines()
        if len(lines) > 1:
            # La primera línea es la cabecera: "Application ID   Version"
            data = []
            for line in lines[1:]:
                line = line.strip()
                if line:
                    # Separar por espacios múltiples
                    parts = line.split(maxsplit=1)
                    if len(parts) == 2:
                        app_id, version = parts
                        data.append(f"{app_id} {version}")
                    elif len(parts) == 1:
                        data.append(f"{parts[0]} (versión no especificada)")
            return "\n".join(sorted(data))
    return None

# ---- Main ----
def main():
    output_file = Path("pkgs.md")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# 📦 Lista completa de paquetes instalados\n\n")
        f.write(f"Generado el: {subprocess.getoutput('date')}\n\n")
        f.write("---\n\n")

        # APT
        apt_list = get_apt_packages()
        write_section(f, "APT (dpkg)", apt_list, is_table=False)

        # Snap
        snap_list = get_snap_packages()
        write_section(f, "Snap", snap_list, is_table=False)

        # Flatpak
        flatpak_list = get_flatpak_packages()
        write_section(f, "Flatpak", flatpak_list, is_table=False)

        f.write("---\n")
        f.write("> ℹ️ **Nota:** Este script solo incluye gestores populares (APT, Snap, Flatpak).\n")
        f.write("> Si utilizas otros (pip, npm, AppImage, etc.) deberás añadirlos manualmente.\n")

    print(f"✅ Listado guardado en: {output_file.absolute()}")

if __name__ == "__main__":
    main()