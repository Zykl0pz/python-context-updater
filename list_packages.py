#!/usr/bin/env python3
"""
Lista todos los paquetes instalados en el sistema (Linux, macOS, Windows)
soportando múltiples gestores. Salida en MD, JSON, XML, TXT o estadísticas.
Modo interactivo o línea de comandos. Guarda perfiles.
"""

import subprocess
import sys
import platform
from pathlib import Path
import shutil
import json
import re
import os
import argparse
import logging
import getpass
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from path_manager import get_repo_dir, get_script_dir, get_instance_dir, get_global_profile_path, get_log_path, get_cache_dir

# ─── Dependencias opcionales ───────────────────────────────────────────────
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# ─── Colores ANSI ──────────────────────────────────────────────────────────
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def colored(text, color):
    if sys.stdout.isatty():
        return f"{color}{text}{Colors.ENDC}"
    return text

# ─── Logging ───────────────────────────────────────────────────────────────
logger = logging.getLogger('pkg_list')
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('pkg_list.log', encoding='utf-8')
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(fh)
logger.addHandler(ch)

# ─── Utilidades generales ──────────────────────────────────────────────────
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

def run_powershell(command):
    """Ejecuta un comando de PowerShell en Windows y devuelve stdout."""
    if get_os() != 'windows':
        return None
    full_cmd = f'powershell -NoProfile -Command "{command}"'
    out, err, code = run_command(full_cmd)
    return out if code == 0 else None

# ─── Linux: APT ────────────────────────────────────────────────────────────
def linux_apt():
    if not command_exists('dpkg-query'):
        return None
    out, _, code = run_command("dpkg-query -W -f='${Package} ${Version}\\n'")
    if code == 0 and out:
        return "\n".join(sorted(out.splitlines()))
    return None

def linux_apt_ppas():
    out, _, code = run_command("grep -rhE '^deb ' /etc/apt/sources.list.d/ 2>/dev/null")
    if code == 0 and out:
        return out
    return None

# ─── Linux: Snap ───────────────────────────────────────────────────────────
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

# ─── Linux: Flatpak ────────────────────────────────────────────────────────
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

# ─── Linux: Pacman (Arch) ──────────────────────────────────────────────────
def linux_pacman():
    if not command_exists('pacman'):
        return None
    out, _, code = run_command("pacman -Q")
    if code == 0 and out:
        return "\n".join(sorted(out.splitlines()))
    return None

# ─── Linux: DNF (Fedora/RHEL) ──────────────────────────────────────────────
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

# ─── Linux: YUM (legacy) ───────────────────────────────────────────────────
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

# ─── Linux: Zypper (OpenSUSE) ──────────────────────────────────────────────
def linux_zypper():
    if not command_exists('zypper'):
        return None
    out, _, code = run_command("zypper se --installed-only 2>/dev/null")
    if code == 0 and out:
        lines = []
        for line in out.splitlines():
            if '|' in line and not line.startswith('+--'):
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 3:
                    name = parts[1]
                    version = parts[2].split()[0]
                    if name and name not in ('Name', 'S'):
                        lines.append(f"{name} {version}")
        return "\n".join(sorted(lines))
    return None

# ─── Linux: RPM (genérico) ─────────────────────────────────────────────────
def linux_rpm():
    if not command_exists('rpm'):
        return None
    out, _, code = run_command("rpm -qa --queryformat '%{NAME} %{VERSION}\\n'")
    if code == 0 and out:
        return "\n".join(sorted(out.splitlines()))
    return None

# ─── Linux: AppImage (escaneo directorios) ─────────────────────────────────
def linux_appimage():
    home = str(Path.home())
    dirs = [f"{home}/Applications", f"{home}/AppImages", "/opt/appimages"]
    results = []
    for d in dirs:
        apps = scan_directory_for_appimages(d)
        if apps:
            results.append(f"# {d}\n{apps}")
    return "\n\n".join(results) if results else None

# ─── Linux: GNU Stow ───────────────────────────────────────────────────────
def linux_gnu_stow():
    stow_dir = "/usr/local/stow"
    if os.path.isdir(stow_dir):
        try:
            pkgs = [d for d in os.listdir(stow_dir) if os.path.isdir(os.path.join(stow_dir, d))]
            if pkgs:
                return "\n".join(sorted(pkgs))
        except:
            pass
    return None

# ─── macOS: Homebrew ───────────────────────────────────────────────────────
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

# ─── macOS: MacPorts ───────────────────────────────────────────────────────
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

# ─── macOS: pkgutil (paquetes .pkg) ────────────────────────────────────────
def macos_pkgutil():
    out, _, code = run_command("pkgutil --pkgs")
    if code == 0 and out:
        return "\n".join(sorted(out.splitlines()))
    return None

# ─── macOS: Mac App Store (mas) ────────────────────────────────────────────
def macos_mas():
    if not command_exists('mas'):
        return None
    out, _, code = run_command("mas list")
    if code == 0 and out:
        lines = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.match(r"\d+\s+(.+)\s\((.+)\)", line)
            if match:
                name, version = match.groups()
                lines.append(f"{name} {version}")
            else:
                lines.append(line)
        return "\n".join(sorted(lines))
    return None

# ─── macOS: launchctl (agentes/daemons) ────────────────────────────────────
def macos_launchctl():
    out, _, code = run_command("launchctl list")
    if code == 0 and out:
        lines = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 3:
                label = parts[2]
                lines.append(label)
        return "\n".join(sorted(lines)) if lines else None
    return None

# ─── macOS: system_profiler (aplicaciones .app) ────────────────────────────
def macos_system_profiler():
    out, _, code = run_command("system_profiler SPApplicationsDataType")
    if code == 0 and out:
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

# ─── Windows: winget ───────────────────────────────────────────────────────
def windows_winget():
    if not command_exists('winget'):
        return None
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

# ─── Windows: Chocolatey ───────────────────────────────────────────────────
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

# ─── Windows: Scoop ────────────────────────────────────────────────────────
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

# ─── Windows: Registro (programas MSI/EXE) ─────────────────────────────────
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

# ─── Windows: WSL ──────────────────────────────────────────────────────────
def windows_wsl():
    if not command_exists('wsl'):
        return None
    out, _, code = run_command("wsl --list --verbose")
    if code == 0 and out:
        lines = out.splitlines()
        if len(lines) > 1:
            return "\n".join(lines[1:])
    return None

# ─── Windows: Extensiones VS Code ──────────────────────────────────────────
def windows_vscode_extensions():
    if not command_exists('code'):
        return None
    out, _, code = run_command("code --list-extensions")
    if code == 0 and out:
        return out
    return None

# ─── Windows: Módulos PowerShell instalados ────────────────────────────────
def windows_powershell_modules():
    out = run_powershell("Get-InstalledModule | Select-Object -Property Name,Version | Format-List")
    if out:
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

# ─── Windows: Características opcionales de Windows ────────────────────────
def windows_features():
    out = run_powershell("Get-WindowsOptionalFeature -Online | Where-Object {$_.State -eq 'Enabled'} | Select-Object FeatureName")
    if out:
        lines = [line.strip() for line in out.splitlines() if line.strip() and not line.startswith("FeatureName")]
        return "\n".join(sorted(lines)) if lines else None
    return None

# ─── Multiplataforma: asdf ─────────────────────────────────────────────────
def generic_asdf():
    if not command_exists('asdf'):
        return None
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
                versions = [v.strip(' *') for v in ver_out.splitlines() if v.strip()]
                for v in versions:
                    result.append(f"{plugin} {v}")
            else:
                result.append(f"{plugin} (no versions)")
    return "\n".join(sorted(result)) if result else None

# ─── Multiplataforma: Nix ──────────────────────────────────────────────────
def generic_nix():
    if not command_exists('nix-env'):
        return None
    out, _, code = run_command("nix-env -q")
    if code == 0 and out:
        return out
    if command_exists('nix'):
        out2, _, code2 = run_command("nix profile list")
        if code2 == 0 and out2:
            return out2
    return None

# ─── Multiplataforma: Guix ─────────────────────────────────────────────────
def generic_guix():
    if not command_exists('guix'):
        return None
    out, _, code = run_command("guix package --list-installed")
    if code == 0 and out:
        return out
    return None

# ─── Multiplataforma: pip (Python) ─────────────────────────────────────────
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

# ─── Multiplataforma: npm (Node.js) ────────────────────────────────────────
def generic_npm():
    if not command_exists('npm'):
        return None
    out, _, code = run_command("npm list -g --depth=0")
    if code == 0 and out:
        packages = []
        for line in out.splitlines():
            if '──' in line:
                pkg_part = line.split('──')[-1].strip()
                if '@' in pkg_part:
                    name, version = pkg_part.split('@', 1)
                    packages.append(f"{name} {version}")
                else:
                    packages.append(pkg_part)
        return "\n".join(sorted(packages)) if packages else None
    return None

# ─── Multiplataforma: gem (Ruby) ───────────────────────────────────────────
def generic_gem():
    if not command_exists('gem'):
        return None
    out, _, code = run_command("gem list")
    if code == 0 and out:
        packages = []
        for line in out.splitlines():
            match = re.match(r"(\S+)\s+\((.+)\)", line)
            if match:
                name, versions = match.groups()
                first_version = versions.split(',')[0].strip()
                packages.append(f"{name} {first_version}")
            else:
                packages.append(line)
        return "\n".join(sorted(packages)) if packages else None
    return None

# ─── Multiplataforma: cargo (Rust) ─────────────────────────────────────────
def generic_cargo():
    if not command_exists('cargo'):
        return None
    out, _, code = run_command("cargo install --list")
    if code == 0 and out:
        packages = []
        for line in out.splitlines():
            line = line.strip()
            if line and not line.startswith("cargo"):
                parts = line.split()
                if parts and len(parts) >= 2:
                    name = parts[0]
                    version = parts[1].strip(':')
                    packages.append(f"{name} {version}")
        return "\n".join(sorted(packages)) if packages else None
    return None

# ─── Lista completa de gestores (nombre, función, sistema operativo) ───────
MANAGERS = [
    # Linux
    ("APT (dpkg)", linux_apt, "linux"),
    ("PPAs (repositorios)", linux_apt_ppas, "linux"),
    ("Snap", linux_snap, "linux"),
    ("Flatpak", linux_flatpak, "linux"),
    ("Pacman (Arch)", linux_pacman, "linux"),
    ("DNF (Fedora/RHEL)", linux_dnf, "linux"),
    ("YUM (legacy)", linux_yum, "linux"),
    ("Zypper (OpenSUSE)", linux_zypper, "linux"),
    ("RPM (genérico)", linux_rpm, "linux"),
    ("AppImage (escaneo)", linux_appimage, "linux"),
    ("GNU Stow", linux_gnu_stow, "linux"),
    # macOS
    ("Homebrew", macos_brew, "macos"),
    ("MacPorts", macos_macports, "macos"),
    ("pkgutil (.pkg)", macos_pkgutil, "macos"),
    ("Mac App Store (mas)", macos_mas, "macos"),
    ("LaunchAgents/LaunchDaemons", macos_launchctl, "macos"),
    ("Aplicaciones .app", macos_system_profiler, "macos"),
    # Windows
    ("winget", windows_winget, "windows"),
    ("Chocolatey", windows_chocolatey, "windows"),
    ("Scoop", windows_scoop, "windows"),
    ("Registro Windows (MSI/EXE)", windows_registry, "windows"),
    ("WSL distribuciones", windows_wsl, "windows"),
    ("Extensiones VS Code", windows_vscode_extensions, "windows"),
    ("Módulos PowerShell", windows_powershell_modules, "windows"),
    ("Características Windows", windows_features, "windows"),
    # Multiplataforma
    ("asdf", generic_asdf, "common"),
    ("Nix", generic_nix, "common"),
    ("Guix", generic_guix, "common"),
    ("pip (Python)", generic_pip, "common"),
    ("npm (Node.js global)", generic_npm, "common"),
    ("gem (Ruby)", generic_gem, "common"),
    ("cargo (Rust)", generic_cargo, "common"),
]

# ─── Funciones de escritura (múltiples formatos) ───────────────────────────
def write_output_md(results, metadata, stats, output_file="packages.md"):
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# 📦 Lista de paquetes instalados\n\n")
        f.write(f"**Generado:** {metadata['generated']}  \n")
        f.write(f"**Sistema:** {metadata['system']}  \n")
        f.write(f"**Usuario:** {metadata['user']}  \n")
        f.write(f"**Directorio:** {metadata['cwd']}  \n\n")
        f.write("## 📊 Estadísticas\n\n")
        f.write(f"- **Total de gestores:** {stats['total_managers']}\n")
        f.write(f"- **Total de paquetes (estimado):** {stats['total_packages']}\n\n")
        f.write("## 📦 Paquetes por gestor\n\n")
        for mgr_name, content in results:
            if content is None:
                continue
            f.write(f"### {mgr_name}\n\n")
            f.write("```\n")
            # Limitar a 1M caracteres por gestor (por si acaso)
            f.write(content[:1000000])
            f.write("\n```\n\n")
        f.write("---\n")
        f.write("> ℹ️ Nota: Algunos gestores pueden requerir privilegios de administrador.\n")
    return output_file

def write_output_json(results, metadata, stats, output_file="packages.json"):
    data = {
        "metadata": metadata,
        "stats": stats,
        "packages": {mgr: content if content else None for mgr, content in results}
    }
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return output_file

def write_output_xml(results, metadata, stats, output_file="packages.xml"):
    import xml.etree.ElementTree as ET
    root = ET.Element("packages")
    meta = ET.SubElement(root, "metadata")
    for k, v in metadata.items():
        elem = ET.SubElement(meta, k)
        elem.text = str(v)
    stats_elem = ET.SubElement(root, "statistics")
    for k, v in stats.items():
        elem = ET.SubElement(stats_elem, k)
        elem.text = str(v)
    for mgr_name, content in results:
        mgr_elem = ET.SubElement(root, "manager", name=mgr_name)
        if content:
            mgr_elem.text = content
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(output_file, encoding='utf-8', xml_declaration=True)
    return output_file

def write_output_txt(results, metadata, stats, output_file="packages.txt"):
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"LISTA DE PAQUETES INSTALADOS\n")
        f.write(f"Generado: {metadata['generated']}\n")
        f.write(f"Sistema: {metadata['system']}\n")
        f.write(f"Usuario: {metadata['user']}\n")
        f.write(f"Directorio: {metadata['cwd']}\n\n")
        f.write(f"Total de gestores: {stats['total_managers']}\n")
        f.write(f"Total de paquetes (estimado): {stats['total_packages']}\n\n")
        for mgr_name, content in results:
            if content is None:
                continue
            f.write(f"=== {mgr_name} ===\n")
            f.write(content)
            f.write("\n\n")
    return output_file

def write_output_stats(results, metadata, stats, output_file="packages_stats.json"):
    # Solo guarda estadísticas
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({"metadata": metadata, "stats": stats}, f, indent=2)
    return output_file

# ─── Cálculo de estadísticas ───────────────────────────────────────────────
def compute_stats(results):
    total_packages = 0
    mgr_count = 0
    for mgr, content in results:
        if content and content.strip():
            mgr_count += 1
            # Estimación: contar líneas no vacías como paquetes (aproximado)
            total_packages += len([l for l in content.splitlines() if l.strip()])
    return {
        "total_managers": mgr_count,
        "total_packages": total_packages,
    }

# ─── Interfaz de usuario: argumentos CLI e interactivo ─────────────────────
def parse_args():
    parser = argparse.ArgumentParser(description="Lista paquetes instalados en múltiples formatos")
    parser.add_argument("--format", "-f", choices=["md", "json", "xml", "txt", "stats"], default=None,
                        help="Formato de salida")
    parser.add_argument("--output", "-o", help="Archivo de salida (sin extensión, se añade automáticamente)")
    parser.add_argument("--quiet", "-q", action="store_true", help="Modo silencioso (sin preguntas)")
    parser.add_argument("--profile", "-p", help="Cargar perfil desde archivo (por defecto .pkg_profile.json)")
    parser.add_argument("--save-profile", action="store_true", help="Guardar configuración como perfil")
    parser.add_argument("--include-manager", nargs="+", help="Solo estos gestores (nombres exactos)")
    parser.add_argument("--exclude-manager", nargs="+", help="Excluir estos gestores")
    parser.add_argument("--no-parallel", action="store_true", help="Deshabilitar ejecución paralela")
    return parser.parse_args()

def interactive_selection():
    print(colored("\n=== Listado de paquetes instalados - Modo interactivo ===", Colors.HEADER))
    print("Selecciona los gestores que quieres consultar (pueden tardar unos segundos):")
    current_os = get_os()
    available = []
    for name, func, os_type in MANAGERS:
        if os_type == "common" or os_type == current_os:
            available.append(name)
    for i, name in enumerate(available, 1):
        print(f"{i:2d}. {name}")
    print("\nOpciones: 'all', 'none', o números separados por comas (ej. 1,3,5)")
    while True:
        sel = input(colored("Tu selección: ", Colors.CYAN)).strip().lower()
        if sel == 'all':
            selected = available
            break
        elif sel == 'none':
            selected = []
            break
        else:
            try:
                idxs = [int(x.strip()) for x in sel.split(',')]
                selected = [available[i-1] for i in idxs if 1 <= i <= len(available)]
                if selected:
                    break
                else:
                    print(colored("Selección vacía o inválida.", Colors.WARNING))
            except ValueError:
                print(colored("Entrada no válida.", Colors.WARNING))
    print("\nFormatos disponibles: md, json, xml, txt, stats")
    fmt = input(colored("Formato de salida [md]: ", Colors.CYAN)).strip().lower() or "md"
    if fmt not in ("md","json","xml","txt","stats"):
        fmt = "md"
    out_base = input(colored("Nombre base del archivo (sin extensión) [packages]: ", Colors.CYAN)).strip() or "packages"
    parallel = input(colored("¿Ejecutar en paralelo? (s/n) [s]: ", Colors.CYAN)).strip().lower() != "n"
    save = input(colored("¿Guardar este perfil? (s/n) [n]: ", Colors.CYAN)).strip().lower() == "s"
    return {
        "selected_managers": selected,
        "format": fmt,
        "output_base": out_base,
        "parallel": parallel,
        "save_profile": save
    }

def load_profile(profile_path=".pkg_profile.json"):
    if os.path.isfile(profile_path):
        try:
            with open(profile_path, 'r') as f:
                return json.load(f)
        except:
            pass
    return None

def save_profile(profile, profile_path=".pkg_profile.json"):
    try:
        with open(profile_path, 'w') as f:
            json.dump(profile, f, indent=2)
        logger.info(colored(f"Perfil guardado en {profile_path}", Colors.GREEN))
    except Exception as e:
        logger.warning(f"No se pudo guardar perfil: {e}")

# ─── Main ──────────────────────────────────────────────────────────────────
def main():
    args = parse_args()
    profile = None
    if args.profile:
        profile = load_profile(args.profile)
    elif not args.quiet and not args.format:
        # Modo interactivo
        profile = interactive_selection()
    else:
        # Modo CLI puro
        profile = {}
        current_os = get_os()
        all_managers = [name for name, func, os_type in MANAGERS if os_type == "common" or os_type == current_os]
        if args.include_manager:
            profile["selected_managers"] = [m for m in all_managers if m in args.include_manager]
        else:
            profile["selected_managers"] = all_managers
        if args.exclude_manager:
            profile["selected_managers"] = [m for m in profile["selected_managers"] if m not in args.exclude_manager]
        profile["format"] = args.format or "md"
        profile["output_base"] = args.output or "packages"
        profile["parallel"] = not args.no_parallel
        profile["save_profile"] = args.save_profile

    if not profile.get("selected_managers"):
        logger.error("No se seleccionó ningún gestor. Saliendo.")
        return

    # Preparar lista de gestores a ejecutar
    managers_to_run = []
    for name, func, os_type in MANAGERS:
        if name in profile["selected_managers"]:
            managers_to_run.append((name, func))

    logger.info(colored(f"Consultando {len(managers_to_run)} gestores...", Colors.CYAN))

    # Ejecutar en paralelo o secuencial
    results = []
    if profile["parallel"] and len(managers_to_run) > 1:
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_mgr = {executor.submit(func): name for name, func in managers_to_run}
            if HAS_TQDM:
                pbar = tqdm(total=len(managers_to_run), desc="Consultando gestores", unit="gestor")
            for future in as_completed(future_to_mgr):
                name = future_to_mgr[future]
                content = future.result()
                results.append((name, content))
                if HAS_TQDM:
                    pbar.update(1)
            if HAS_TQDM:
                pbar.close()
    else:
        for name, func in managers_to_run:
            logger.debug(f"Ejecutando {name}...")
            content = func()
            results.append((name, content))

    # Estadísticas
    stats = compute_stats(results)

    # Metadatos
    metadata = {
        "generated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "system": platform.platform(),
        "user": getpass.getuser(),
        "cwd": os.getcwd(),
        "python_version": sys.version
    }

    # Generar archivo de salida
    fmt = profile["format"]
    out_base = profile["output_base"]
    out_file = None
    if fmt == "md":
        out_file = write_output_md(results, metadata, stats, f"{out_base}.md")
    elif fmt == "json":
        out_file = write_output_json(results, metadata, stats, f"{out_base}.json")
    elif fmt == "xml":
        out_file = write_output_xml(results, metadata, stats, f"{out_base}.xml")
    elif fmt == "txt":
        out_file = write_output_txt(results, metadata, stats, f"{out_base}.txt")
    elif fmt == "stats":
        out_file = write_output_stats(results, metadata, stats, f"{out_base}_stats.json")
    else:
        out_file = write_output_md(results, metadata, stats, "packages.md")

    logger.info(colored(f"✅ Archivo generado: {out_file}", Colors.GREEN))

    # Guardar perfil si se pidió
    if profile.get("save_profile"):
        save_profile({
            "selected_managers": profile["selected_managers"],
            "format": fmt,
            "output_base": out_base,
            "parallel": profile["parallel"]
        })

    # Resumen
    print(colored("\n=== RESUMEN ===", Colors.BOLD))
    print(f"Gestores consultados: {len([r for r in results if r[1] is not None])}/{len(results)}")
    print(f"Total paquetes estimado: {stats['total_packages']}")
    print(f"Salida: {out_file}")

if __name__ == '__main__':
    main()