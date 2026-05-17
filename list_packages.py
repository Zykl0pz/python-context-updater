#!/usr/bin/env python3
"""
Script multiplataforma para listar paquetes instalados en el sistema.
Soporta decenas de gestores y fuentes en Linux, macOS y Windows.

Uso: python3 list_all_packages.py
Salida: pkgs.md (archivo Markdown)
"""

import subprocess
import sys
import platform
from pathlib import Path
import shutil
import json
import re
import os

# ---- Detección de SO ----
def get_os():
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
def run_command(cmd, shell=True, timeout=30):
    try:
        result = subprocess.run(cmd, shell=shell, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", f"Timeout after {timeout}s", -1
    except Exception as e:
        return "", str(e), -1

def command_exists(cmd):
    return shutil.which(cmd) is not None

def write_section(f, title, content, code_block=True):
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

def run_powershell(command):
    """Ejecuta un comando de PowerShell en Windows y devuelve stdout."""
    if get_os() != 'windows':
        return None
    full_cmd = f'powershell -NoProfile -Command "{command}"'
    out, err, code = run_command(full_cmd)
    return out if code == 0 else None

def scan_directory_for_appimages(directory):
    """Escanea un directorio en busca de archivos .AppImage (Linux)."""
    if not os.path.isdir(directory):
        return None
    try:
        files = [f for f in os.listdir(directory) if f.endswith('.AppImage')]
        if files:
            return "\n".join(sorted(files))
    except:
        pass
    return None

# ---- Linux específico ----
def linux_apt():
    if not command_exists('dpkg-query'):
        return None
    out, _, code = run_command("dpkg-query -W -f='${Package} ${Version}\\n'")
    if code == 0 and out:
        return "\n".join(sorted(out.splitlines()))
    return None

def linux_apt_ppas():
    """Lista los PPAs (repositorios personales) añadidos al sistema."""
    out, _, code = run_command("grep -rhE '^deb ' /etc/apt/sources.list.d/ 2>/dev/null")
    if code == 0 and out:
        return out
    return None

def linux_snap():
    if not command_exists('snap'):
        return None
    out, _, code = run_command("snap list")
    if code != 0 or not out:
        return None
    lines = out.splitlines()
    if len(lines) <= 1:
        return None
    packages = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 2:
            packages.append(f"{parts[0]} {parts[1]}")
    return "\n".join(sorted(packages))

def linux_flatpak():
    if not command_exists('flatpak'):
        return None
    out, _, code = run_command("flatpak list --columns=application,version")
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
    if not command_exists('pacman'):
        return None
    out, _, code = run_command("pacman -Q")
    if code == 0 and out:
        return "\n".join(sorted(out.splitlines()))
    return None

def linux_dnf():
    if not command_exists('dnf'):
        return None
    out, _, code = run_command("dnf list installed --quiet 2>/dev/null")
    if code == 0 and out:
        lines = []
        for line in out.splitlines():
            if line.strip():
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0].split('.')[0]
                    version = parts[1]
                    lines.append(f"{name} {version}")
        return "\n".join(sorted(lines))
    return None

def linux_yum():
    if not command_exists('yum'):
        return None
    out, _, code = run_command("yum list installed -q 2>/dev/null")
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

def linux_zypper():
    if not command_exists('zypper'):
        return None
    out, _, code = run_command("zypper se --installed-only 2>/dev/null")
    if code == 0 and out:
        # El formato tiene cabeceras. Buscamos líneas con '|' (tabla)
        lines = []
        for line in out.splitlines():
            if '|' in line and not line.startswith('+--'):
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 3:
                    name = parts[1]
                    version = parts[2].split()[0]  # a veces hay más texto
                    if name and name not in ('Name', 'S'):
                        lines.append(f"{name} {version}")
        return "\n".join(sorted(lines))
    return None

def linux_rpm():
    if not command_exists('rpm'):
        return None
    out, _, code = run_command("rpm -qa --queryformat '%{NAME} %{VERSION}\\n'")
    if code == 0 and out:
        return "\n".join(sorted(out.splitlines()))
    return None

def linux_appimage():
    """Busca AppImages en ~/Applications y ~/AppImages."""
    home = str(Path.home())
    dirs = [f"{home}/Applications", f"{home}/AppImages", "/opt/appimages"]
    results = []
    for d in dirs:
        apps = scan_directory_for_appimages(d)
        if apps:
            results.append(f"# {d}\n{apps}")
    return "\n\n".join(results) if results else None

def linux_gnu_stow():
    """Lista los paquetes gestionados con GNU Stow (por defecto en /usr/local/stow)."""
    stow_dir = "/usr/local/stow"
    if os.path.isdir(stow_dir):
        try:
            pkgs = [d for d in os.listdir(stow_dir) if os.path.isdir(os.path.join(stow_dir, d))]
            if pkgs:
                return "\n".join(sorted(pkgs))
        except:
            pass
    return None

# ---- macOS específico ----
def macos_brew():
    if not command_exists('brew'):
        return None
    out, _, code = run_command("brew list --versions")
    if code == 0 and out:
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
    if not command_exists('port'):
        return None
    out, _, code = run_command("port installed")
    if code == 0 and out:
        lines = []
        for line in out.splitlines():
            line = line.strip()
            match = re.match(r"(\S+)\s+@(\S+)", line)
            if match:
                name, version = match.groups()
                lines.append(f"{name} {version}")
        return "\n".join(sorted(lines))
    return None

def macos_pkgutil():
    out, _, code = run_command("pkgutil --pkgs")
    if code == 0 and out:
        return "\n".join(sorted(out.splitlines()))
    return None

def macos_mas():
    """Mac App Store apps (requiere mas CLI)."""
    if not command_exists('mas'):
        return None
    out, _, code = run_command("mas list")
    if code == 0 and out:
        # Formato: "123456789  App Name (1.2.3)"
        lines = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            # Extraer nombre y versión
            match = re.match(r"\d+\s+(.+)\s\((.+)\)", line)
            if match:
                name, version = match.groups()
                lines.append(f"{name} {version}")
            else:
                lines.append(line)
        return "\n".join(sorted(lines))
    return None

def macos_launchctl():
    """Lista agentes y demonios cargados (user). No requiere sudo."""
    out, _, code = run_command("launchctl list")
    if code == 0 and out:
        # Formato: PID    Status  Label
        lines = []
        for line in out.splitlines()[1:]:  # saltar cabecera
            parts = line.split()
            if len(parts) >= 3:
                label = parts[2]
                lines.append(label)
        return "\n".join(sorted(lines)) if lines else None
    return None

def macos_system_profiler():
    """Lista todas las aplicaciones .app instaladas."""
    out, _, code = run_command("system_profiler SPApplicationsDataType")
    if code == 0 and out:
        # Extraer líneas con "Location:" o "Version:" es complejo; mejor buscar nombres
        # Versión simplificada: extraer líneas con "Location:" y el nombre de la app
        apps = set()
        lines = out.splitlines()
        current_app = None
        for line in lines:
            if line.strip().startswith("Location:"):
                loc = line.split(":", 1)[1].strip()
                if loc.endswith(".app"):
                    app_name = os.path.basename(loc)
                    apps.add(app_name)
        return "\n".join(sorted(apps)) if apps else None
    return None

# ---- Windows específico ----
def windows_winget():
    if not command_exists('winget'):
        return None
    # Intentar con JSON
    out, _, code = run_command("winget list --disable-interactivity --output json")
    if code == 0 and out:
        try:
            data = json.loads(out)
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
    if not command_exists('choco'):
        return None
    out, _, code = run_command("choco list --local-only --limit-output")
    if code == 0 and out:
        packages = []
        for line in out.splitlines():
            if '|' in line:
                pkg, ver = line.split('|', 1)
                packages.append(f"{pkg} {ver}")
        return "\n".join(sorted(packages))
    return None

def windows_scoop():
    if not command_exists('scoop'):
        return None
    out, _, code = run_command("scoop list")
    if code == 0 and out:
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
    try:
        import winreg
    except ImportError:
        return None
    packages = set()
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
                            if display_name:
                                try:
                                    display_version = winreg.QueryValueEx(subkey, "DisplayVersion")[0]
                                except:
                                    display_version = "?"
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

def windows_wsl():
    """Lista distribuciones WSL instaladas."""
    if not command_exists('wsl'):
        return None
    out, _, code = run_command("wsl --list --verbose")
    if code == 0 and out:
        lines = out.splitlines()
        # Saltar cabecera "  NAME      STATE           VERSION"
        if len(lines) > 1:
            return "\n".join(lines[1:])
    return None

def windows_vscode_extensions():
    """Extensiones de VS Code instaladas."""
    if not command_exists('code'):
        return None
    out, _, code = run_command("code --list-extensions")
    if code == 0 and out:
        return out
    return None

def windows_powershell_modules():
    """Módulos de PowerShell instalados."""
    out = run_powershell("Get-InstalledModule | Select-Object -Property Name,Version | Format-List")
    if out:
        # Parsear: Name: xxx, Version: yyy
        modules = []
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("Name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("Version:"):
                version = line.split(":", 1)[1].strip()
                modules.append(f"{name} {version}")
        return "\n".join(sorted(modules)) if modules else None
    return None

def windows_features():
    """Características opcionales de Windows (requiere admin)."""
    out = run_powershell("Get-WindowsOptionalFeature -Online | Where-Object {$_.State -eq 'Enabled'} | Select-Object FeatureName")
    if out:
        lines = [line.strip() for line in out.splitlines() if line.strip() and not line.startswith("FeatureName")]
        return "\n".join(sorted(lines)) if lines else None
    return None

# ---- Multiplataforma (cualquier SO) ----
def generic_asdf():
    if not command_exists('asdf'):
        return None
    # Listar plugins y sus versiones instaladas
    out, _, code = run_command("asdf plugin list")
    if code != 0 or not out:
        return None
    plugins = out.splitlines()
    result = []
    for plugin in plugins:
        plugin = plugin.strip()
        if plugin:
            ver_out, _, _ = run_command(f"asdf list {plugin}")
            if ver_out:
                # Eliminar asteriscos y espacios
                versions = [v.strip(' *') for v in ver_out.splitlines() if v.strip()]
                for v in versions:
                    result.append(f"{plugin} {v}")
            else:
                result.append(f"{plugin} (no versions)")
    return "\n".join(sorted(result)) if result else None

def generic_nix():
    if not command_exists('nix-env'):
        return None
    out, _, code = run_command("nix-env -q")
    if code == 0 and out:
        return out
    # También probar nix profile
    if command_exists('nix'):
        out2, _, code2 = run_command("nix profile list")
        if code2 == 0 and out2:
            return out2
    return None

def generic_guix():
    if not command_exists('guix'):
        return None
    out, _, code = run_command("guix package --list-installed")
    if code == 0 and out:
        return out
    return None

def generic_pip():
    if command_exists('pip3'):
        out, _, code = run_command("pip3 list --format=freeze")
        if code == 0 and out:
            return out
    elif command_exists('pip'):
        out, _, code = run_command("pip list --format=freeze")
        if code == 0 and out:
            return out
    return None

def generic_npm():
    if not command_exists('npm'):
        return None
    out, _, code = run_command("npm list -g --depth=0")
    if code == 0 and out:
        # La salida tiene árbol, extraemos líneas con ──
        packages = []
        for line in out.splitlines():
            if '──' in line:
                # Formato: "├── package@version"
                pkg_part = line.split('──')[-1].strip()
                if '@' in pkg_part:
                    name, version = pkg_part.split('@', 1)
                    packages.append(f"{name} {version}")
                else:
                    packages.append(pkg_part)
        return "\n".join(sorted(packages)) if packages else None
    return None

def generic_gem():
    if not command_exists('gem'):
        return None
    out, _, code = run_command("gem list")
    if code == 0 and out:
        # Formato: "package (version, otherversion)"
        packages = []
        for line in out.splitlines():
            match = re.match(r"(\S+)\s+\((.+)\)", line)
            if match:
                name, versions = match.groups()
                # Tomar la primera versión
                first_version = versions.split(',')[0].strip()
                packages.append(f"{name} {first_version}")
            else:
                packages.append(line)
        return "\n".join(sorted(packages)) if packages else None
    return None

def generic_cargo():
    if not command_exists('cargo'):
        return None
    out, _, code = run_command("cargo install --list")
    if code == 0 and out:
        # Extraer líneas que contienen nombres de paquetes
        packages = []
        for line in out.splitlines():
            line = line.strip()
            if line and not line.startswith("cargo"):
                # Formato: "package v0.1.0:"
                parts = line.split()
                if parts and len(parts) >= 2:
                    name = parts[0]
                    version = parts[1].strip(':')
                    packages.append(f"{name} {version}")
        return "\n".join(sorted(packages)) if packages else None
    return None

# ---- Main ----
def main():
    os_name = get_os()
    output_file = Path("pkgs.md")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# 📦 Lista completa de paquetes instalados\n\n")
        f.write(f"**Sistema operativo:** {platform.system()} {platform.release()}\n")
        if os_name == 'windows':
            date_cmd = 'date /t'
        else:
            date_cmd = 'date'
        f.write(f"**Generado el:** {subprocess.getoutput(date_cmd)}\n\n")
        f.write("---\n\n")

        # SECCIONES POR SO
        if os_name == 'linux':
            f.write("## 🐧 Linux (gestores nativos)\n\n")
            write_section(f, "APT (dpkg)", linux_apt())
            write_section(f, "PPAs (repositorios)", linux_apt_ppas())
            write_section(f, "Snap", linux_snap())
            write_section(f, "Flatpak", linux_flatpak())
            write_section(f, "Pacman (Arch)", linux_pacman())
            write_section(f, "DNF (Fedora/RHEL)", linux_dnf())
            write_section(f, "YUM (legacy)", linux_yum())
            write_section(f, "Zypper (OpenSUSE)", linux_zypper())
            write_section(f, "RPM (genérico)", linux_rpm())
            write_section(f, "AppImage", linux_appimage())
            write_section(f, "GNU Stow", linux_gnu_stow())

        elif os_name == 'macos':
            f.write("## 🍎 macOS (gestores nativos)\n\n")
            write_section(f, "Homebrew", macos_brew())
            write_section(f, "MacPorts", macos_macports())
            write_section(f, "pkgutil (.pkg)", macos_pkgutil())
            write_section(f, "Mac App Store (mas)", macos_mas())
            write_section(f, "LaunchAgents/LaunchDaemons (usuario)", macos_launchctl())
            write_section(f, "Aplicaciones .app (system_profiler)", macos_system_profiler())

        elif os_name == 'windows':
            f.write("## 🪟 Windows (gestores nativos)\n\n")
            write_section(f, "winget", windows_winget())
            write_section(f, "Chocolatey", windows_chocolatey())
            write_section(f, "Scoop", windows_scoop())
            write_section(f, "Programas del registro (MSI/EXE)", windows_registry(), code_block=False)
            write_section(f, "WSL (distribuciones)", windows_wsl())
            write_section(f, "Extensiones de VS Code", windows_vscode_extensions())
            write_section(f, "Módulos de PowerShell (instalados)", windows_powershell_modules())
            write_section(f, "Características de Windows (activadas)", windows_features())

        # SECCIÓN MULTIPLATAFORMA (común a todos los SO)
        f.write("\n## 🌐 Gestores multiplataforma\n\n")
        write_section(f, "asdf (version manager)", generic_asdf())
        write_section(f, "Nix (nix-env / profile)", generic_nix())
        write_section(f, "Guix", generic_guix())
        write_section(f, "pip (Python)", generic_pip())
        write_section(f, "npm (Node.js global)", generic_npm())
        write_section(f, "gem (Ruby)", generic_gem())
        write_section(f, "cargo (Rust)", generic_cargo())

        f.write("\n---\n")
        f.write("> ℹ️ **Nota:** Se han listado los paquetes de decenas de gestores.\n")
        f.write("> Algunos comandos requieren permisos de administrador para mostrarse completamente.\n")
        f.write("> Los paquetes pueden aparecer duplicados si están gestionados por múltiples herramientas.\n")

    print(f"✅ Listado guardado en: {output_file.absolute()}")

if __name__ == "__main__":
    main()