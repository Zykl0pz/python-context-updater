#!/usr/bin/env python3
"""
Script multiplataforma para listar paquetes instalados en el sistema.
Soporta:
- Linux: APT, Snap, Flatpak, Pacman (Arch), DNF (Fedora), YUM (antiguo)
- macOS: Homebrew, MacPorts, pkgutil
- Windows: winget, Chocolatey, Scoop, programas del registro (instaladores MSI/EXE)

Los resultados se guardan en 'pkgs.md' con formato Markdown.
"""

import subprocess
import sys
import platform
from pathlib import Path
import shutil
import json
import re

# ---- Detección de SO ----
def get_os():
    """Devuelve 'linux', 'windows' o 'darwin' (macOS)."""
    system = platform.system().lower()
    if system == 'linux':
        return 'linux'
    elif system == 'windows':
        return 'windows'
    elif system == 'darwin':
        return 'macos'
    else:
        return 'unknown'

# ---- Utilidades ----
def run_command(cmd, shell=True):
    """Ejecuta un comando y devuelve (stdout, stderr, returncode)."""
    try:
        result = subprocess.run(cmd, shell=shell, capture_output=True, text=True)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except Exception as e:
        return "", str(e), -1

def command_exists(cmd):
    """Verifica si un comando está disponible en el PATH."""
    return shutil.which(cmd) is not None

def write_section(f, title, content, code_block=True):
    """Escribe una sección en el archivo Markdown."""
    f.write(f"## {title}\n\n")
    if content is None:
        f.write("⚠️ No se pudo obtener la lista o el gestor no está instalado.\n\n")
    elif not content.strip():
        f.write("✅ No hay paquetes instalados con este gestor.\n\n")
    else:
        if code_block:
            f.write("```\n")
            f.write(content)
            f.write("\n```\n")
        else:
            f.write(content)
        f.write("\n")

# ---- Linux ----
def linux_apt():
    """Paquetes APT (Debian/Ubuntu)."""
    if not command_exists('dpkg-query'):
        return None
    out, err, code = run_command("dpkg-query -W -f='${Package} ${Version}\\n'")
    if code == 0 and out:
        lines = sorted(out.splitlines())
        return "\n".join(lines)
    return None

def linux_snap():
    """Paquetes Snap."""
    if not command_exists('snap'):
        return None
    out, err, code = run_command("snap list")
    if code != 0 or not out:
        return None
    lines = out.splitlines()
    if len(lines) <= 1:
        return None
    # Saltar cabecera
    packages = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 2:
            packages.append(f"{parts[0]} {parts[1]}")
    return "\n".join(sorted(packages))

def linux_flatpak():
    """Aplicaciones Flatpak."""
    if not command_exists('flatpak'):
        return None
    out, err, code = run_command("flatpak list --columns=application,version")
    if code != 0 or not out:
        return None
    lines = out.splitlines()
    if len(lines) <= 1:
        return None
    packages = []
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            packages.append(f"{parts[0]} {parts[1]}")
        else:
            packages.append(f"{parts[0]} (sin versión)")
    return "\n".join(sorted(packages))

def linux_pacman():
    """Arch Linux / Manjaro."""
    if not command_exists('pacman'):
        return None
    out, err, code = run_command("pacman -Q")
    if code == 0 and out:
        lines = sorted(out.splitlines())
        return "\n".join(lines)
    return None

def linux_dnf():
    """Fedora / RHEL 8+."""
    if not command_exists('dnf'):
        return None
    out, err, code = run_command("dnf list installed --quiet")
    if code == 0 and out:
        # El formato es "nombre.arquitectura    versión    repositorio"
        lines = []
        for line in out.splitlines():
            if line.strip():
                # Quitamos arquitectura y repo, dejamos nombre y versión
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0].split('.')[0]  # quitar .arch
                    version = parts[1]
                    lines.append(f"{name} {version}")
        return "\n".join(sorted(lines))
    return None

def linux_yum():
    """RHEL 7 y anteriores."""
    if not command_exists('yum'):
        return None
    out, err, code = run_command("yum list installed -q")
    if code == 0 and out:
        lines = []
        for line in out.splitlines():
            if line.strip() and not line.startswith("Installed Packages"):
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0].split('.')[0]
                    version = parts[1]
                    lines.append(f"{name} {version}")
        return "\n".join(sorted(lines))
    return None

# ---- macOS ----
def macos_brew():
    """Homebrew."""
    if not command_exists('brew'):
        return None
    out, err, code = run_command("brew list --versions")
    if code == 0 and out:
        # Formato: "package version version version..." (puede tener múltiples versiones)
        lines = []
        for line in out.splitlines():
            parts = line.split()
            if parts:
                pkg = parts[0]
                version = parts[1] if len(parts) > 1 else "unknown"
                lines.append(f"{pkg} {version}")
        return "\n".join(sorted(lines))
    return None

def macos_macports():
    """MacPorts."""
    if not command_exists('port'):
        return None
    out, err, code = run_command("port installed")
    if code == 0 and out:
        # Limpiar líneas como "  pkgname @version (active)"
        lines = []
        for line in out.splitlines():
            line = line.strip()
            if line and not line.startswith("The following ports are currently installed:"):
                # Extraer nombre y versión
                match = re.match(r"(\S+)\s+@(\S+)", line)
                if match:
                    name, version = match.groups()
                    lines.append(f"{name} {version}")
        return "\n".join(sorted(lines))
    return None

def macos_pkgutil():
    """Paquetes .pkg instalados (sistema)."""
    out, err, code = run_command("pkgutil --pkgs")
    if code == 0 and out:
        lines = sorted(out.splitlines())
        return "\n".join(lines)
    return None

# ---- Windows ----
def windows_winget():
    """Windows Package Manager (winget) - requiere instalación."""
    if not command_exists('winget'):
        return None
    # winget list produce salida con cabeceras, usamos --disable-interactivity
    out, err, code = run_command("winget list --disable-interactivity")
    if code != 0 or not out:
        return None
    lines = out.splitlines()
    # Buscar la línea que separa cabeceras (normalmente después de ---)
    data_start = 0
    for i, line in enumerate(lines):
        if '---' in line:
            data_start = i + 1
            break
    packages = []
    for line in lines[data_start:]:
        line = line.strip()
        if not line or line.startswith("Nombre") or line.startswith("Name"):
            continue
        # Formato típico: "Nombre  Id  Versión  Disponible"
        parts = line.split()
        if len(parts) >= 3:
            # El nombre puede tener espacios, así que no es trivial.
            # Usamos regex: todo hasta el primer espacio, pero mejor usar columnas fijas?
            # Alternativa: salida JSON
            # Probamos con JSON
            break  # Mejor usar JSON
    # Mejor usar JSON para winget
    out_json, err, code = run_command("winget list --disable-interactivity --output json")
    if code == 0 and out_json:
        try:
            data = json.loads(out_json)
            packages = []
            for pkg in data.get("Packages", []):
                name = pkg.get("Name", "?")
                version = pkg.get("Version", "?")
                packages.append(f"{name} {version}")
            return "\n".join(sorted(packages))
        except:
            pass
    return None

def windows_chocolatey():
    """Chocolatey."""
    if not command_exists('choco'):
        return None
    out, err, code = run_command("choco list --local-only --limit-output")
    if code == 0 and out:
        # Formato: paquete|versión
        packages = []
        for line in out.splitlines():
            if '|' in line:
                pkg, ver = line.split('|', 1)
                packages.append(f"{pkg} {ver}")
        return "\n".join(sorted(packages))
    return None

def windows_scoop():
    """Scoop."""
    if not command_exists('scoop'):
        return None
    out, err, code = run_command("scoop list")
    if code == 0 and out:
        # La salida tiene formato tabla con cabeceras "Name  Version  Source"
        lines = out.splitlines()
        packages = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("---") or line.startswith("Name"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                version = parts[1]
                packages.append(f"{name} {version}")
        return "\n".join(sorted(packages))
    return None

def windows_registry():
    """Programas instalados (desinstaladores) desde el registro de Windows."""
    try:
        import winreg
    except ImportError:
        return None
    packages = set()
    # Claves del registro donde se guardan los programas instalados
    uninstall_paths = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ]
    for hkey in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
        for path in uninstall_paths:
            try:
                key = winreg.OpenKey(hkey, path, 0, winreg.KEY_READ)
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        subkey = winreg.OpenKey(key, subkey_name)
                        try:
                            display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                            display_version = winreg.QueryValueEx(subkey, "DisplayVersion")[0] if winreg.QueryValueEx(subkey, "DisplayVersion")[0] else "?"
                            if display_name:
                                packages.add(f"{display_name} {display_version}")
                        except:
                            pass
                        finally:
                            subkey.Close()
                        i += 1
                    except OSError:
                        break
                key.Close()
            except:
                pass
    return "\n".join(sorted(packages)) if packages else None

# ---- Main multiplataforma ----
def main():
    os_name = get_os()
    output_file = Path("pkgs.md")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# 📦 Lista completa de paquetes instalados\n\n")
        f.write(f"**Sistema operativo:** {platform.system()} {platform.release()}\n")
        f.write(f"**Generado el:** {subprocess.getoutput('date' if os_name != 'windows' else 'date /t')}\n\n")
        f.write("---\n\n")

        if os_name == 'linux':
            f.write("## 🐧 Linux\n\n")
            # APT
            apt = linux_apt()
            write_section(f, "APT (dpkg)", apt)
            # Snap
            snap = linux_snap()
            write_section(f, "Snap", snap)
            # Flatpak
            flatpak = linux_flatpak()
            write_section(f, "Flatpak", flatpak)
            # Pacman (Arch)
            pacman = linux_pacman()
            write_section(f, "Pacman (Arch)", pacman)
            # DNF (Fedora)
            dnf = linux_dnf()
            write_section(f, "DNF (Fedora/RHEL)", dnf)
            # YUM
            yum = linux_yum()
            write_section(f, "YUM (legacy)", yum)

        elif os_name == 'macos':
            f.write("## 🍎 macOS\n\n")
            brew = macos_brew()
            write_section(f, "Homebrew", brew)
            macports = macos_macports()
            write_section(f, "MacPorts", macports)
            pkgutil = macos_pkgutil()
            write_section(f, "Paquetes .pkg (sistema)", pkgutil)

        elif os_name == 'windows':
            f.write("## 🪟 Windows\n\n")
            winget = windows_winget()
            write_section(f, "winget (Windows Package Manager)", winget)
            choco = windows_chocolatey()
            write_section(f, "Chocolatey", choco)
            scoop = windows_scoop()
            write_section(f, "Scoop", scoop)
            registry = windows_registry()
            write_section(f, "Programas instalados (Registro de Windows)", registry, code_block=False)

        else:
            f.write("## ❌ Sistema operativo no soportado\n\n")
            f.write("Este script no reconoce tu sistema operativo. Solo soporta Linux, macOS y Windows.\n")

        f.write("\n---\n")
        f.write("> ℹ️ **Nota:** Se listan los paquetes de los gestores más comunes.\n")
        f.write("> Es posible que algunos paquetes aparezcan duplicados si están gestionados por múltiples herramientas.\n")

    print(f"✅ Listado guardado en: {output_file.absolute()}")

if __name__ == "__main__":
    main()