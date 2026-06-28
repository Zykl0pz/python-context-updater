#!/usr/bin/env python3
"""
Inventario Forense Completo + Árbol de Directorios (sin bloqueos en Windows).
Extrae: hardware (CPU, RAM, discos SMART, batería, monitor), SO, kernel,
red (WiFi, proxy, firewall), paquetes (30+ gestores), procesos, usuarios,
logs, historiales de shell, persistencia, certificados, impresoras,
bluetooth, unidades montadas, copias de sombra, y genera un árbol de
directorios de todo el sistema.
Salida en JSON, MD, TXT, XML o estadísticas.
"""

import os
import sys
import platform
import subprocess
import json
import re
import shutil
import argparse
import logging
import getpass
import glob
import fnmatch
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional, Tuple

# ─── Dependencias opcionales ───────────────────────────────────────────────
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

try:
    import pathspec
    HAS_PATHSPEC = True
except ImportError:
    HAS_PATHSPEC = False

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

# ─── Logging ──────────────────────────────────────────────────────────────
logger = logging.getLogger('forensic_inventory')
logger.setLevel(logging.DEBUG)
log_dir = Path.home() / ".forensic_inventory"
log_dir.mkdir(exist_ok=True)
fh = logging.FileHandler(log_dir / "forensic.log", encoding='utf-8')
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(fh)
logger.addHandler(ch)

# ─── Utilidades generales ──────────────────────────────────────────────────
def run_command(cmd: str, shell: bool = True, timeout: int = 30) -> Tuple[str, str, int]:
    try:
        result = subprocess.run(cmd, shell=shell, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", f"Timeout after {timeout}s", -1
    except Exception as e:
        return "", str(e), -1

def command_exists(cmd: str) -> bool:
    return shutil.which(cmd) is not None

def get_os() -> str:
    system = platform.system().lower()
    if system == 'linux':
        return 'linux'
    elif system == 'windows':
        return 'windows'
    elif system == 'darwin':
        return 'macos'
    else:
        return 'unknown'

def run_powershell(command: str) -> Optional[str]:
    """Ejecuta un comando de PowerShell en Windows sin interacción."""
    if get_os() != 'windows':
        return None
    full_cmd = f'powershell -NoProfile -NonInteractive -Command "{command}"'
    try:
        result = subprocess.run(
            full_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            stdin=subprocess.DEVNULL
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout en PowerShell: {command[:100]}")
        return None
    except Exception as e:
        logger.warning(f"Error en PowerShell: {e}")
        return None

def read_file_if_exists(path: str) -> Optional[str]:
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read().strip()
        except:
            pass
    return None

def format_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

# ─── Funciones de árbol de directorios ──────────────────────────────────
DEFAULT_IGNORED_DIRS = {
    '__pycache__', 'node_modules', 'dist', 'out', 'build',
    'venv', 'env', '.git', '.svn', '.hg', '.idea', '.vscode', 'vendor', 'samples', 'old'
}

def is_always_ignored_dir(dirname):
    return dirname in DEFAULT_IGNORED_DIRS

def should_ignore_hidden_dir(dirname):
    return dirname.startswith('.')

def generate_directory_tree(start_path='.', show_hidden=True, max_depth=10):
    lines = []
    lines.append(os.path.abspath(start_path))

    def walk_dir(current_path, prefix="", depth=0):
        if depth > max_depth:
            lines.append(prefix + "└── [máxima profundidad]")
            return
        try:
            items = os.listdir(current_path)
        except PermissionError:
            lines.append(prefix + "└── [Permiso denegado]")
            return
        dirs, files = [], []
        for item in items:
            full = os.path.join(current_path, item)
            if os.path.isdir(full) and is_always_ignored_dir(item):
                continue
            if not show_hidden and should_ignore_hidden_dir(item):
                continue
            if os.path.isdir(full):
                dirs.append(item)
            else:
                files.append(item)
        dirs.sort()
        files.sort()
        for i, d in enumerate(dirs):
            last = (i == len(dirs)-1) and (len(files) == 0)
            conn = "└── " if last else "├── "
            lines.append(prefix + conn + d + "/")
            new_prefix = prefix + "    " if last else prefix + "│   "
            walk_dir(os.path.join(current_path, d), new_prefix, depth+1)
        for i, f in enumerate(files):
            last = (i == len(files)-1)
            conn = "└── " if last else "├── "
            full = os.path.join(current_path, f)
            try:
                size = format_size(os.path.getsize(full))
            except OSError:
                size = "???"
            lines.append(f"{prefix}{conn}{f} ({size})")

    walk_dir(start_path)
    return '\n'.join(lines)

# ==========================================================================
# SECCIÓN 1: FUNCIONES DE PAQUETES (30+ GESTORES)
# ==========================================================================

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

def linux_rpm():
    if not command_exists('rpm'):
        return None
    out, _, code = run_command("rpm -qa --queryformat '%{NAME} %{VERSION}\\n'")
    if code == 0 and out:
        return "\n".join(sorted(out.splitlines()))
    return None

def linux_appimage():
    home = str(Path.home())
    dirs = [f"{home}/Applications", f"{home}/AppImages", "/opt/appimages"]
    results = []
    for d in dirs:
        if os.path.isdir(d):
            try:
                apps = [f for f in os.listdir(d) if f.endswith('.AppImage')]
                if apps:
                    results.append(f"# {d}\n" + "\n".join(sorted(apps)))
            except:
                pass
    return "\n\n".join(results) if results else None

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

def macos_system_profiler_apps():
    out, _, code = run_command("system_profiler SPApplicationsDataType")
    if code == 0 and out:
        apps = set()
        for line in out.splitlines():
            if line.strip().startswith("Location:"):
                loc = line.split(":", 1)[1].strip()
                if loc.endswith(".app"):
                    app_name = os.path.basename(loc)
                    apps.add(app_name)
        return "\n".join(sorted(apps)) if apps else None
    return None

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
        packages = []
        for line in out.splitlines():
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

def windows_registry_packages():
    if not HAS_WINREG:
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
    if not command_exists('wsl'):
        return None
    out, _, code = run_command("wsl --list --verbose")
    if code == 0 and out:
        lines = out.splitlines()
        if len(lines) > 1:
            return "\n".join(lines[1:])
    return None

def windows_vscode_extensions():
    if not command_exists('code'):
        return None
    out, _, code = run_command("code --list-extensions")
    if code == 0 and out:
        return out
    return None

def windows_powershell_modules():
    if get_os() != 'windows':
        return None
    out = run_powershell("Get-InstalledModule -ErrorAction SilentlyContinue | Select-Object -Property Name,Version | Format-List")
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

def windows_features():
    if get_os() != 'windows':
        return None
    out = run_powershell("Get-WindowsOptionalFeature -Online -ErrorAction SilentlyContinue | Where-Object {$_.State -eq 'Enabled'} | Select-Object FeatureName")
    if out:
        lines = [line.strip() for line in out.splitlines() if line.strip() and not line.startswith("FeatureName")]
        return "\n".join(sorted(lines)) if lines else None
    return None

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

def get_complete_package_list() -> Dict[str, Any]:
    packages = {}
    os_type = get_os()
    if os_type == 'linux':
        packages['dpkg_apt'] = linux_apt()
        packages['apt_ppas'] = linux_apt_ppas()
        packages['snap'] = linux_snap()
        packages['flatpak'] = linux_flatpak()
        packages['pacman'] = linux_pacman()
        packages['dnf'] = linux_dnf()
        packages['yum'] = linux_yum()
        packages['zypper'] = linux_zypper()
        packages['rpm'] = linux_rpm()
        packages['appimages'] = linux_appimage()
        packages['gnu_stow'] = linux_gnu_stow()
    elif os_type == 'macos':
        packages['homebrew'] = macos_brew()
        packages['macports'] = macos_macports()
        packages['pkgutil_pkg'] = macos_pkgutil()
        packages['mas_appstore'] = macos_mas()
        packages['launch_agents_daemons'] = macos_launchctl()
        packages['applications_app'] = macos_system_profiler_apps()
    elif os_type == 'windows':
        packages['winget'] = windows_winget()
        packages['chocolatey'] = windows_chocolatey()
        packages['scoop'] = windows_scoop()
        packages['registry_msi_exe'] = windows_registry_packages()
        packages['wsl_distributions'] = windows_wsl()
        packages['vscode_extensions'] = windows_vscode_extensions()
        packages['powershell_modules'] = windows_powershell_modules()
        packages['windows_features'] = windows_features()
    packages['asdf'] = generic_asdf()
    packages['nix'] = generic_nix()
    packages['guix'] = generic_guix()
    packages['pip_python'] = generic_pip()
    packages['npm_nodejs_global'] = generic_npm()
    packages['gem_ruby'] = generic_gem()
    packages['cargo_rust'] = generic_cargo()
    return packages

# ==========================================================================
# SECCIÓN 2: INFORMACIÓN DEL SISTEMA
# ==========================================================================

def get_system_info() -> Dict[str, Any]:
    info = {}
    os_type = get_os()
    info['os_type'] = os_type
    info['os_platform'] = platform.platform()
    info['os_release'] = platform.release()
    info['os_version'] = platform.version()
    info['machine'] = platform.machine()
    info['processor'] = platform.processor()
    info['hostname'] = platform.node()
    info['system'] = platform.system()
    info['python_version'] = sys.version
    info['boot_time'] = None
    if HAS_PSUTIL:
        info['boot_time'] = datetime.fromtimestamp(psutil.boot_time()).isoformat()
    if os_type == 'linux':
        osrelease = read_file_if_exists('/etc/os-release')
        if osrelease:
            info['os_release_info'] = {}
            for line in osrelease.splitlines():
                if '=' in line:
                    k, v = line.split('=', 1)
                    info['os_release_info'][k] = v.strip('"')
        installer_log = read_file_if_exists('/var/log/installer/syslog')
        if installer_log:
            lines = installer_log.splitlines()
            if lines:
                info['install_date_approx'] = lines[0][:15]
        uname = os.uname()
        info['kernel'] = {
            'sysname': uname.sysname,
            'nodename': uname.nodename,
            'release': uname.release,
            'version': uname.version,
            'machine': uname.machine
        }
    elif os_type == 'windows':
        out, _, _ = run_command('systeminfo | findstr /B /C:"OS Name" /C:"OS Version" /C:"System Type" /C:"Install Date"')
        if out:
            info['windows_systeminfo'] = out
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
            install_date = winreg.QueryValueEx(key, "InstallDate")[0]
            info['install_date'] = datetime.fromtimestamp(install_date).isoformat()
            winreg.CloseKey(key)
        except:
            pass
    elif os_type == 'macos':
        sw_vers, _, _ = run_command('sw_vers')
        info['sw_vers'] = sw_vers
        sysctl_out, _, _ = run_command('sysctl kern.version kern.osrevision')
        info['sysctl'] = sysctl_out
    return info

# ==========================================================================
# SECCIÓN 3: HARDWARE
# ==========================================================================

def get_hardware_info() -> Dict[str, Any]:
    hw = {}
    os_type = get_os()
    cpu = {}
    if HAS_PSUTIL:
        cpu['physical_cores'] = psutil.cpu_count(logical=False)
        cpu['logical_cores'] = psutil.cpu_count(logical=True)
        cpu['max_freq'] = psutil.cpu_freq().max if psutil.cpu_freq() else None
        cpu['min_freq'] = psutil.cpu_freq().min if psutil.cpu_freq() else None
        cpu['current_freq'] = psutil.cpu_freq().current if psutil.cpu_freq() else None
        cpu['usage_per_core'] = psutil.cpu_percent(percpu=True, interval=0.5)
        cpu['avg_usage'] = psutil.cpu_percent(interval=0.5)
    if os_type == 'linux':
        model = read_file_if_exists('/proc/cpuinfo')
        if model:
            for line in model.splitlines():
                if 'model name' in line:
                    cpu['model'] = line.split(':', 1)[1].strip()
                    break
        cache = read_file_if_exists('/sys/devices/system/cpu/cpu0/cache/index0/size')
        if cache:
            cpu['cache_l1'] = cache
        cpuinfo = read_file_if_exists('/proc/cpuinfo')
        if cpuinfo:
            cpu['cpuinfo'] = cpuinfo
    elif os_type == 'windows':
        out, _, _ = run_command('wmic cpu get name, maxclockspeed, numberofcores, numberoflogicalprocessors /format:csv')
        if out:
            cpu['wmic_cpu'] = out
    elif os_type == 'macos':
        out, _, _ = run_command('sysctl machdep.cpu.brand_string')
        if out:
            cpu['model'] = out.split(':', 1)[1].strip()
    hw['cpu'] = cpu

    mem = {}
    if HAS_PSUTIL:
        mem['total'] = psutil.virtual_memory().total
        mem['available'] = psutil.virtual_memory().available
        mem['used'] = psutil.virtual_memory().used
        mem['percent'] = psutil.virtual_memory().percent
        mem['swap_total'] = psutil.swap_memory().total
        mem['swap_used'] = psutil.swap_memory().used
        mem['swap_percent'] = psutil.swap_memory().percent
    if os_type == 'linux' and command_exists('dmidecode'):
        out, _, _ = run_command('sudo dmidecode -t memory 2>/dev/null')
        if out:
            mem['dmidecode_memory'] = out
    elif os_type == 'windows':
        out, _, _ = run_command('wmic memorychip get banklabel, capacity, speed, memorytype, formfactor /format:csv')
        if out:
            mem['wmic_memory'] = out
    hw['memory'] = mem

    mobo = {}
    if os_type == 'linux' and command_exists('dmidecode'):
        out, _, _ = run_command('sudo dmidecode -t baseboard 2>/dev/null')
        if out:
            mobo['baseboard'] = out
        out, _, _ = run_command('sudo dmidecode -t bios 2>/dev/null')
        if out:
            mobo['bios'] = out
        out, _, _ = run_command('sudo dmidecode -t system 2>/dev/null')
        if out:
            mobo['system'] = out
    elif os_type == 'windows':
        out, _, _ = run_command('wmic baseboard get manufacturer, product, serialnumber /format:csv')
        if out:
            mobo['wmic_baseboard'] = out
        out, _, _ = run_command('wmic bios get manufacturer, name, serialnumber, version /format:csv')
        if out:
            mobo['wmic_bios'] = out
    elif os_type == 'macos':
        out, _, _ = run_command('system_profiler SPHardwareDataType')
        if out:
            mobo['system_profiler_hardware'] = out
    hw['motherboard'] = mobo

    disks = []
    if HAS_PSUTIL:
        for part in psutil.disk_partitions():
            disk = {
                'device': part.device,
                'mountpoint': part.mountpoint,
                'fstype': part.fstype,
                'opts': part.opts,
            }
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disk['total'] = usage.total
                disk['used'] = usage.used
                disk['free'] = usage.free
                disk['percent'] = usage.percent
            except:
                pass
            disks.append(disk)
    hw['disk_partitions'] = disks

    physical_disks = []
    if os_type == 'linux':
        out, _, _ = run_command('lsblk -o NAME,SIZE,MODEL,SERIAL,TYPE /dev/sd* /dev/nvme* 2>/dev/null')
        if out:
            physical_disks.append({'lsblk': out})
        if command_exists('smartctl'):
            out, _, _ = run_command('ls /dev/sd* /dev/nvme* 2>/dev/null')
            devices = out.splitlines()
            for dev in devices:
                smart_out, _, _ = run_command(f'sudo smartctl -a {dev} 2>/dev/null')
                if smart_out:
                    disk_info = {'device': dev, 'smartctl': smart_out}
                    attr = {}
                    for line in smart_out.splitlines():
                        if 'Power-On Hours' in line or 'Power_On_Hours' in line:
                            parts = line.split()
                            if len(parts) >= 10:
                                attr['power_on_hours'] = parts[9]
                        if 'Power Cycle Count' in line or 'Power_Cycle_Count' in line:
                            parts = line.split()
                            if len(parts) >= 10:
                                attr['power_cycle_count'] = parts[9]
                        if 'Wear Leveling Count' in line:
                            parts = line.split()
                            if len(parts) >= 10:
                                attr['wear_leveling'] = parts[9]
                        if 'Temperature' in line or 'Temperature_Celsius' in line:
                            parts = line.split()
                            if len(parts) >= 10:
                                attr['temperature'] = parts[9]
                        if 'Available_Reservd_Space' in line or 'Percentage Used' in line:
                            parts = line.split()
                            if len(parts) >= 10:
                                attr['percentage_used'] = parts[9]
                    disk_info['smart_attributes'] = attr
                    physical_disks.append(disk_info)
    elif os_type == 'windows':
        ps = run_powershell("Get-PhysicalDisk -ErrorAction SilentlyContinue | Select-Object DeviceID, MediaType, Model, SerialNumber, Size, OperationalStatus | ConvertTo-Json")
        if ps:
            try:
                disk_data = json.loads(ps)
                physical_disks.append({'powerShell_physical_disk': disk_data})
            except:
                pass
        out, _, _ = run_command('wmic diskdrive get model, size, serialnumber, status /format:csv')
        if out:
            physical_disks.append({'wmic_diskdrive': out})
    elif os_type == 'macos':
        out, _, _ = run_command('system_profiler SPStorageDataType')
        if out:
            physical_disks.append({'system_profiler_storage': out})
        if command_exists('smartctl'):
            out, _, _ = run_command('diskutil list | grep "/dev/disk"')
            devices = re.findall(r'/dev/disk\d+', out)
            for dev in devices:
                smart_out, _, _ = run_command(f'sudo smartctl -a {dev} 2>/dev/null')
                if smart_out:
                    disk_info = {'device': dev, 'smartctl': smart_out}
                    physical_disks.append(disk_info)
    hw['physical_disks'] = physical_disks

    gpu = {}
    if os_type == 'linux':
        out, _, _ = run_command('lspci -v | grep -i "VGA" -A 10')
        if out:
            gpu['lspci'] = out
        if command_exists('nvidia-smi'):
            out, _, _ = run_command('nvidia-smi --query-gpu=name,driver_version,memory.total,temperature.gpu,utilization.gpu --format=csv')
            if out:
                gpu['nvidia_smi'] = out
    elif os_type == 'windows':
        out, _, _ = run_command('wmic path win32_VideoController get name, driverversion, currenthorizontalresolution, currentverticalresolution /format:csv')
        if out:
            gpu['wmic_video'] = out
    elif os_type == 'macos':
        out, _, _ = run_command('system_profiler SPDisplaysDataType')
        if out:
            gpu['system_profiler_display'] = out
    hw['gpu'] = gpu

    perif = {}
    if os_type == 'linux':
        out, _, _ = run_command('lsusb -v 2>/dev/null')
        if out:
            perif['lsusb'] = out
        out, _, _ = run_command('lspci -v 2>/dev/null')
        if out:
            perif['lspci'] = out
    elif os_type == 'windows':
        out, _, _ = run_command('wmic path Win32_USBControllerDevice get Dependent /format:csv')
        if out:
            perif['wmic_usb'] = out
    hw['peripherals'] = perif

    sensors = {}
    if os_type == 'linux':
        if command_exists('sensors'):
            out, _, _ = run_command('sensors')
            if out:
                sensors['sensors'] = out
    hw['sensors'] = sensors
    return hw

# ==========================================================================
# SECCIÓN 4: FUNCIONES FORENSES ADICIONALES (corregidas)
# ==========================================================================

def get_battery_info() -> Dict[str, Any]:
    battery = {}
    os_type = get_os()
    if os_type == 'linux':
        bat_path = '/sys/class/power_supply/BAT0'
        if os.path.isdir(bat_path):
            for attr in ['cycle_count', 'energy_full', 'energy_full_design', 'serial_number', 'manufacture_date', 'model_name']:
                val = read_file_if_exists(os.path.join(bat_path, attr))
                if val:
                    battery[attr] = val
            energy_now = read_file_if_exists(os.path.join(bat_path, 'energy_now'))
            if energy_now and battery.get('energy_full'):
                battery['health_percent'] = f"{int(energy_now) / int(battery['energy_full']) * 100:.1f}%"
    elif os_type == 'windows':
        ps = run_powershell("Get-WmiObject Win32_Battery -ErrorAction SilentlyContinue | Select-Object Name, Manufacturer, SerialNumber, Chemistry, DesignCapacity, FullChargeCapacity, CycleCount, EstimatedChargeRemaining | ConvertTo-Json")
        if ps:
            try:
                battery['wmi'] = json.loads(ps)
            except:
                battery['raw'] = ps
    elif os_type == 'macos':
        out, _, _ = run_command("system_profiler SPPowerDataType | grep -E 'Cycle Count|Health|Serial|Manufacturer'")
        if out:
            battery['system_profiler'] = out
        out, _, _ = run_command("ioreg -l -r | grep -E 'CycleCount|DesignCapacity|MaxCapacity'")
        if out:
            battery['ioreg'] = out
    return battery

def get_monitor_info() -> Dict[str, Any]:
    monitor = {}
    os_type = get_os()
    if os_type == 'linux':
        edid_paths = glob.glob('/sys/class/drm/*/edid')
        for path in edid_paths:
            try:
                with open(path, 'rb') as f:
                    edid_raw = f.read()
                if edid_raw:
                    if command_exists('edid-decode'):
                        out, _, _ = run_command(f"edid-decode {path}")
                        if out:
                            monitor[os.path.basename(os.path.dirname(path))] = out
                    else:
                        monitor[os.path.basename(os.path.dirname(path))] = edid_raw.hex()
            except:
                pass
    elif os_type == 'windows':
        ps = run_powershell("Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorID -ErrorAction SilentlyContinue | Select-Object SerialNumberID, ProductCodeID, WeekOfManufacture, YearOfManufacture | ConvertTo-Json")
        if ps:
            try:
                monitor['wmi_edid'] = json.loads(ps)
            except:
                monitor['raw'] = ps
    elif os_type == 'macos':
        out, _, _ = run_command("system_profiler SPDisplaysDataType | grep -E 'Display Serial|Manufacturer'")
        if out:
            monitor['system_profiler'] = out
    return monitor

def get_firewall_info() -> Dict[str, Any]:
    fw = {}
    os_type = get_os()
    if os_type == 'linux':
        if command_exists('iptables'):
            out, _, _ = run_command("iptables -L -n -v")
            if out:
                fw['iptables'] = out
        if command_exists('nft'):
            out, _, _ = run_command("nft list ruleset")
            if out:
                fw['nftables'] = out
        if command_exists('ufw'):
            out, _, _ = run_command("ufw status verbose")
            if out:
                fw['ufw'] = out
    elif os_type == 'windows':
        ps = run_powershell("Get-NetFirewallProfile -ErrorAction SilentlyContinue | Select-Object Name, Enabled, DefaultInboundAction, DefaultOutboundAction | ConvertTo-Json")
        if ps:
            fw['firewall_profiles'] = ps
        out, _, _ = run_command("netsh advfirewall show allprofiles")
        if out:
            fw['netsh'] = out
    elif os_type == 'macos':
        out, _, _ = run_command("sudo pfctl -s all 2>/dev/null")
        if out:
            fw['pfctl'] = out
    return fw

def get_updates_info() -> Dict[str, Any]:
    updates = {}
    os_type = get_os()
    if os_type == 'linux':
        apt_hist = read_file_if_exists('/var/log/apt/history.log')
        if apt_hist:
            updates['apt_history'] = apt_hist.splitlines()[-100:]
        if os.path.isdir('/var/log/dnf.history'):
            updates['dnf_logs'] = '\n'.join(os.listdir('/var/log/dnf.history'))
        out, _, _ = run_command("uname -r")
        updates['kernel_version'] = out
    elif os_type == 'windows':
        out, _, _ = run_command("wmic qfe list brief /format:csv")
        if out:
            updates['wmic_hotfixes'] = out
        ps = run_powershell("Get-HotFix -ErrorAction SilentlyContinue | Select-Object HotFixID, InstalledOn, Description | ConvertTo-Json")
        if ps:
            updates['hotfixes'] = ps
    elif os_type == 'macos':
        out, _, _ = run_command("softwareupdate --history 2>/dev/null")
        if out:
            updates['softwareupdate_history'] = out
    return updates

def get_usb_history() -> Dict[str, Any]:
    usb = {}
    os_type = get_os()
    if os_type == 'linux':
        out, _, _ = run_command("dmesg | grep -i usb | grep -E 'New USB device|Product|SerialNumber'")
        if out:
            usb['dmesg_usb'] = out
        out, _, _ = run_command("journalctl -k -g 'usb.*New' --no-pager 2>/dev/null")
        if out:
            usb['journalctl_usb'] = out
        out, _, _ = run_command("lsusb -v 2>/dev/null | grep -E 'idVendor|idProduct|iSerial'")
        if out:
            usb['lsusb_detail'] = out
    elif os_type == 'windows':
        ps = run_powershell("Get-PnpDevice -Class USB -ErrorAction SilentlyContinue | Select-Object FriendlyName, InstanceId, Status | ConvertTo-Json")
        if ps:
            try:
                usb['pnp_usb_devices'] = json.loads(ps)
            except:
                usb['pnp_usb_raw'] = ps
        ps = run_powershell("Get-EventLog -LogName System -Source 'Microsoft-Windows-Kernel-PnP' -Newest 50 -ErrorAction SilentlyContinue | Select-Object TimeGenerated, Message | ConvertTo-Json")
        if ps:
            try:
                usb['pnp_events'] = json.loads(ps)
            except:
                usb['pnp_events_raw'] = ps
    elif os_type == 'macos':
        out, _, _ = run_command("system_profiler SPUSBDataType")
        if out:
            usb['system_profiler_usb'] = out
        out, _, _ = run_command("ioreg -p IOUSB -l -w 0")
        if out:
            usb['ioreg_usb'] = out
    return usb

def get_kernel_modules() -> Dict[str, Any]:
    mods = {}
    os_type = get_os()
    if os_type == 'linux':
        out, _, _ = run_command("lsmod")
        if out:
            mods['lsmod'] = out
        out, _, _ = run_command("modinfo $(lsmod | awk '{print $1}' | tail -n +2) 2>/dev/null | grep -E '^filename|^version|^description'")
        if out:
            mods['modinfo'] = out
    elif os_type == 'windows':
        out, _, _ = run_command("driverquery /v /fo csv")
        if out:
            mods['driverquery'] = out
        ps = run_powershell("Get-WmiObject Win32_PnPSignedDriver -ErrorAction SilentlyContinue | Select-Object DeviceName, DriverVersion, Manufacturer | ConvertTo-Json")
        if ps:
            mods['pnp_drivers'] = ps
    elif os_type == 'macos':
        out, _, _ = run_command("kextstat")
        if out:
            mods['kextstat'] = out
    return mods

def get_secureboot_tpm() -> Dict[str, Any]:
    st = {}
    os_type = get_os()
    if os_type == 'linux':
        if command_exists('mokutil'):
            out, _, _ = run_command("mokutil --sb-state")
            if out:
                st['secure_boot'] = out
        if os.path.exists('/sys/class/tpm/tpm0'):
            st['tpm_present'] = 'yes'
            tpm_version = read_file_if_exists('/sys/class/tpm/tpm0/device/description')
            if tpm_version:
                st['tpm_version'] = tpm_version
    elif os_type == 'windows':
        ps = run_powershell("Confirm-SecureBootUEFI -ErrorAction SilentlyContinue")
        if ps:
            st['secure_boot'] = ps.strip()
        ps = run_powershell("Get-Tpm -ErrorAction SilentlyContinue | Select-Object TpmReady, TpmPresent, TpmVersion | ConvertTo-Json")
        if ps:
            try:
                st['tpm'] = json.loads(ps)
            except:
                st['tpm'] = ps
    elif os_type == 'macos':
        out, _, _ = run_command("csrutil status")
        st['sip_status'] = out
    return st

def get_network_cache() -> Dict[str, Any]:
    cache = {}
    os_type = get_os()
    if os_type == 'linux':
        out, _, _ = run_command("ip neigh show")
        if out:
            cache['arp'] = out
    elif os_type == 'windows':
        out, _, _ = run_command("arp -a")
        if out:
            cache['arp'] = out
        out, _, _ = run_command("ipconfig /displaydns")
        if out:
            cache['dns_cache'] = out
    elif os_type == 'macos':
        out, _, _ = run_command("arp -a")
        if out:
            cache['arp'] = out
    return cache

def get_execution_artifacts():
    artifacts = {}
    if get_os() == 'windows':
        prefetch_dir = "C:\\Windows\\Prefetch"
        if os.path.isdir(prefetch_dir):
            artifacts['prefetch_files'] = os.listdir(prefetch_dir)[:200]
        amcache = "C:\\Windows\\AppCompat\\Programs\\Amcache.hve"
        if os.path.isfile(amcache):
            artifacts['amcache_present'] = True
        ps = run_powershell("Get-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\UserAssist' -ErrorAction SilentlyContinue")
        if ps:
            artifacts['userassist'] = ps
    return artifacts

def get_shell_histories():
    hist = {}
    home = str(Path.home())
    bash_hist = read_file_if_exists(f"{home}/.bash_history")
    if bash_hist:
        hist['bash'] = bash_hist.splitlines()[-500:]
    zsh_hist = read_file_if_exists(f"{home}/.zsh_history")
    if zsh_hist:
        hist['zsh'] = zsh_hist.splitlines()[-500:]
    fish_hist = read_file_if_exists(f"{home}/.local/share/fish/fish_history")
    if fish_hist:
        hist['fish'] = fish_hist.splitlines()[-500:]
    py_hist = read_file_if_exists(f"{home}/.python_history")
    if py_hist:
        hist['python'] = py_hist.splitlines()[-100:]
    mysql_hist = read_file_if_exists(f"{home}/.mysql_history")
    if mysql_hist:
        hist['mysql'] = mysql_hist
    if get_os() == 'windows':
        ps_hist = read_file_if_exists(f"{home}\\AppData\\Roaming\\Microsoft\\Windows\\PowerShell\\PSReadLine\\ConsoleHost_history.txt")
        if ps_hist:
            hist['powershell'] = ps_hist.splitlines()[-500:]
    return hist

def get_trust_relationships():
    trust = {}
    home = str(Path.home())
    ssh_dir = f"{home}/.ssh"
    if os.path.isdir(ssh_dir):
        trust['ssh_keys'] = os.listdir(ssh_dir)
        known = read_file_if_exists(f"{ssh_dir}/known_hosts")
        if known:
            trust['known_hosts'] = known.splitlines()[:100]
        auth = read_file_if_exists(f"{ssh_dir}/authorized_keys")
        if auth:
            trust['authorized_keys'] = auth.splitlines()
    if os.path.isdir(f"{home}/.gnupg"):
        trust['gpg_present'] = True
    gitconf = read_file_if_exists(f"{home}/.gitconfig")
    if gitconf:
        trust['gitconfig'] = gitconf
    return trust

def get_containers_vms():
    virt = {}
    if command_exists('docker'):
        out, _, _ = run_command("docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'")
        if out:
            virt['docker_containers'] = out
        out, _, _ = run_command("docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}'")
        if out:
            virt['docker_images'] = out
    if command_exists('podman'):
        out, _, _ = run_command("podman ps -a")
        if out:
            virt['podman'] = out
    if os.path.isdir('/var/lib/lxc'):
        virt['lxc_present'] = True
    if get_os() == 'windows':
        ps = run_powershell("Get-VM -ErrorAction SilentlyContinue | Select-Object Name, State, MemoryStartup | ConvertTo-Json")
        if ps:
            virt['hyperv_vms'] = ps
    return virt

def get_encryption_status():
    enc = {}
    os_type = get_os()
    if os_type == 'linux' and command_exists('cryptsetup'):
        out, _, _ = run_command("sudo cryptsetup status /dev/mapper/* 2>/dev/null")
        if out:
            enc['luks_status'] = out
        out, _, _ = run_command("sudo cryptsetup luksDump /dev/sd* 2>/dev/null | grep -E 'Version|Created|UUID'")
        if out:
            enc['luks_headers'] = out
    elif os_type == 'windows':
        ps = run_powershell("Get-BitLockerVolume -ErrorAction SilentlyContinue | Select-Object MountPoint, ProtectionStatus, EncryptionPercentage | ConvertTo-Json")
        if ps:
            enc['bitlocker'] = ps
        ps = run_powershell("manage-bde -status -ErrorAction SilentlyContinue")
        if ps:
            enc['manage_bde'] = ps
    elif os_type == 'macos':
        out, _, _ = run_command("fdesetup status")
        if out:
            enc['filevault'] = out
    return enc

def get_recent_documents():
    recent = {}
    home = str(Path.home())
    os_type = get_os()
    if os_type == 'linux':
        recent_file = read_file_if_exists(f"{home}/.local/share/recently-used.xbel")
        if recent_file:
            recent['gnome_recent'] = recent_file.splitlines()[:100]
        if os.path.isdir(f"{home}/.kde/share/apps/RecentDocuments"):
            recent['kde_recent'] = os.listdir(f"{home}/.kde/share/apps/RecentDocuments")
    elif os_type == 'windows':
        recent_dir = f"{home}\\AppData\\Roaming\\Microsoft\\Windows\\Recent"
        if os.path.isdir(recent_dir):
            recent['windows_recent'] = os.listdir(recent_dir)[:100]
        jumplist_dir = f"{home}\\AppData\\Roaming\\Microsoft\\Windows\\Recent\\AutomaticDestinations"
        if os.path.isdir(jumplist_dir):
            recent['jumplists'] = os.listdir(jumplist_dir)
    elif os_type == 'macos':
        recent_dir = f"{home}/Library/Application Support/com.apple.sharedfilelist/com.apple.LSSharedFileList.ApplicationRecentDocuments"
        if os.path.isdir(recent_dir):
            recent['macos_recent'] = os.listdir(recent_dir)
    return recent

def get_stealth_persistence():
    persistence = {}
    os_type = get_os()
    if os_type == 'windows':
        ps = run_powershell("Get-WmiObject -Namespace root\\subscription -Class __EventFilter -ErrorAction SilentlyContinue | Select-Object Name, EventNamespace, Query | ConvertTo-Json")
        if ps:
            persistence['wmi_filters'] = ps
        ps = run_powershell("Get-WmiObject -Namespace root\\subscription -Class CommandLineEventConsumer -ErrorAction SilentlyContinue | Select-Object Name, CommandLineTemplate | ConvertTo-Json")
        if ps:
            persistence['wmi_consumers'] = ps
        out, _, _ = run_command("schtasks /query /fo csv /v")
        persistence['scheduled_tasks_detailed'] = out
    elif os_type == 'linux':
        if command_exists('systemctl'):
            out, _, _ = run_command("systemctl list-timers --all --no-legend")
            persistence['systemd_timers'] = out
            out, _, _ = run_command("systemctl list-units --type=service --all --no-legend | grep -E 'enabled|static'")
            persistence['enabled_services'] = out
        out, _, _ = run_command("atq")
        if out:
            persistence['at_jobs'] = out
    return persistence

def get_browser_metadata():
    browsers = {}
    home = str(Path.home())
    chrome = f"{home}/.config/google-chrome" if get_os()=='linux' else f"{home}/AppData/Local/Google/Chrome/User Data"
    if os.path.isdir(chrome):
        browsers['chrome_present'] = True
        ext_dir = f"{chrome}/Default/Extensions"
        if os.path.isdir(ext_dir):
            browsers['chrome_extensions'] = os.listdir(ext_dir)[:50]
        history_db = f"{chrome}/Default/History"
        if os.path.isfile(history_db):
            browsers['chrome_history_present'] = os.path.getmtime(history_db)
    ff = f"{home}/.mozilla/firefox" if get_os()=='linux' else f"{home}/AppData/Roaming/Mozilla/Firefox/Profiles"
    if os.path.isdir(ff):
        browsers['firefox_present'] = True
    return browsers

def get_security_policies():
    policy = {}
    os_type = get_os()
    if os_type == 'linux':
        out, _, _ = run_command("sestatus")
        if out:
            policy['selinux'] = out
        out, _, _ = run_command("sudo aa-status 2>/dev/null")
        if out:
            policy['apparmor'] = out
        out, _, _ = run_command("sudo auditctl -s 2>/dev/null")
        if out:
            policy['auditd_status'] = out
        out, _, _ = run_command("sysctl -a | grep -E 'net.ipv4.conf|kernel.dmesg_restrict'")
        if out:
            policy['sysctl_hardening'] = out
    elif os_type == 'windows':
        ps = run_powershell("auditpol /get /category:* -ErrorAction SilentlyContinue")
        if ps:
            policy['audit_policies'] = ps
        ps = run_powershell("Get-MpComputerStatus -ErrorAction SilentlyContinue")
        if ps:
            policy['defender_status'] = ps
    return policy

def get_ipc_artifacts():
    ipc = {}
    os_type = get_os()
    if os_type == 'windows':
        ps = run_powershell("Get-CimInstance -ClassName Win32_DCOMApplication -ErrorAction SilentlyContinue | Select-Object Name, AppID | ConvertTo-Json")
        if ps:
            ipc['dcom_apps'] = ps
    elif os_type == 'linux':
        out, _, _ = run_command("dbus-send --system --print-reply --dest=org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus.ListActivatableNames")
        if out:
            ipc['dbus_activatable'] = out
    return ipc

def get_crash_dumps():
    dumps = {}
    os_type = get_os()
    if os_type == 'linux':
        core_dir = '/var/crash'
        if os.path.isdir(core_dir):
            dumps['linux_crashes'] = os.listdir(core_dir)
        if command_exists('coredumpctl'):
            out, _, _ = run_command("coredumpctl list -n 50")
            if out:
                dumps['coredumpctl'] = out
    elif os_type == 'windows':
        minidump = "C:\\Windows\\Minidump"
        if os.path.isdir(minidump):
            dumps['minidumps'] = os.listdir(minidump)[:50]
        live_kernel = "C:\\Windows\\LiveKernelReports"
        if os.path.isdir(live_kernel):
            dumps['live_kernel_reports'] = os.listdir(live_kernel)[:50]
    return dumps

def get_system_file_timestamps():
    stamps = {}
    os_type = get_os()
    if os_type == 'linux':
        critical_files = ['/bin/ls', '/bin/ps', '/bin/netstat', '/usr/bin/find', '/usr/bin/which']
        for f in critical_files:
            if os.path.isfile(f):
                try:
                    stat = os.stat(f)
                    stamps[f] = {
                        'size': stat.st_size,
                        'mtime': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        'ctime': datetime.fromtimestamp(stat.st_ctime).isoformat()
                    }
                except:
                    pass
    elif os_type == 'windows':
        critical = ['C:\\Windows\\System32\\kernel32.dll', 'C:\\Windows\\System32\\ntoskrnl.exe', 'C:\\Windows\\explorer.exe']
        for f in critical:
            if os.path.isfile(f):
                try:
                    stat = os.stat(f)
                    stamps[f] = {
                        'size': stat.st_size,
                        'mtime': datetime.fromtimestamp(stat.st_mtime).isoformat()
                    }
                except:
                    pass
    return stamps

def get_wifi_profiles() -> Dict[str, Any]:
    wifi = {}
    os_type = get_os()
    if os_type == 'windows':
        out, _, _ = run_command("netsh wlan show profiles")
        if out:
            profiles = re.findall(r": (.+)", out)
            wifi['ssids'] = profiles
            details = []
            for ssid in profiles[:20]:
                out2, _, _ = run_command(f'netsh wlan show profile name="{ssid}" | findstr "Security"')
                details.append(f"{ssid} -> {out2.strip() if out2 else 'Unknown'}")
            wifi['security_types'] = details
    elif os_type == 'linux':
        if command_exists('nmcli'):
            out, _, _ = run_command("nmcli -t -f NAME,TYPE connection show --active 2>/dev/null")
            if out:
                wifi['nmcli_active'] = out
            out, _, _ = run_command("nmcli -f NAME connection show 2>/dev/null | grep -v 'NAME'")
            if out:
                wifi['nmcli_all_profiles'] = out.splitlines()[:50]
        nm_connections = '/etc/NetworkManager/system-connections'
        if os.path.isdir(nm_connections):
            wifi['nm_connections_files'] = os.listdir(nm_connections)[:50]
    elif os_type == 'macos':
        out, _, _ = run_command("system_profiler SPAirPortDataType")
        if out:
            wifi['airport_profiles'] = out
        out, _, _ = run_command("defaults read /Library/Preferences/SystemConfiguration/com.apple.airport.preferences | grep SSID")
        if out:
            wifi['ssids_prefs'] = out
    return wifi

def get_network_mounts() -> Dict[str, Any]:
    mounts = {}
    os_type = get_os()
    if os_type == 'windows':
        out, _, _ = run_command("net use")
        if out:
            mounts['net_use'] = out
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Network")
            drives = []
            i = 0
            while True:
                try:
                    drive = winreg.EnumKey(key, i)
                    subkey = winreg.OpenKey(key, drive)
                    try:
                        remote = winreg.QueryValueEx(subkey, "RemotePath")[0]
                        drives.append(f"{drive} -> {remote}")
                    except:
                        pass
                    subkey.Close()
                    i += 1
                except OSError:
                    break
            key.Close()
            if drives:
                mounts['registry_mapped_drives'] = drives
        except:
            pass
    elif os_type == 'linux':
        out, _, _ = run_command("mount -t cifs,nfs,nfs4,smbfs,afp 2>/dev/null")
        if out:
            mounts['mount_cifs_nfs'] = out
        out, _, _ = run_command("df -T | grep -E 'cifs|nfs|smbfs|afp'")
        if out:
            mounts['df_mounts'] = out
        fstab = read_file_if_exists('/etc/fstab')
        if fstab:
            mounts['fstab_entries'] = [l for l in fstab.splitlines() if 'cifs' in l or 'nfs' in l]
    elif os_type == 'macos':
        out, _, _ = run_command("mount -t smbfs,afp,nfs")
        if out:
            mounts['mounts'] = out
    return mounts

def get_installed_certificates() -> Dict[str, Any]:
    certs = {}
    os_type = get_os()
    if os_type == 'windows':
        ps = run_powershell("Get-ChildItem -Path Cert:\\ -Recurse -ErrorAction SilentlyContinue | Select-Object Subject, Issuer, NotAfter, SerialNumber | ConvertTo-Json")
        if ps:
            certs['cert_store_short'] = ps[:5000]
        out, _, _ = run_command("certutil -store root")
        if out:
            certs['root_ca_certutil'] = out[:5000]
    elif os_type == 'linux':
        if os.path.isdir('/etc/ssl/certs'):
            certs['ca_bundle_list'] = os.listdir('/etc/ssl/certs')[:50]
        if command_exists('trust'):
            out, _, _ = run_command("trust list")
            if out:
                certs['trust_list'] = out[:5000]
        if os.path.isdir('/etc/pki/ca-trust'):
            certs['pki_ca_trust'] = os.listdir('/etc/pki/ca-trust')[:50]
    elif os_type == 'macos':
        out, _, _ = run_command("security find-identity -v -p basic")
        if out:
            certs['security_identities'] = out
    return certs

def get_printers_info() -> Dict[str, Any]:
    printers = {}
    os_type = get_os()
    if os_type == 'windows':
        ps = run_powershell("Get-WmiObject Win32_Printer -ErrorAction SilentlyContinue | Select-Object Name, PortName, DriverName, Network | ConvertTo-Json")
        if ps:
            printers['wmi_printers'] = ps
        out, _, _ = run_command("wmic printer get name, portname, shared, network /format:csv")
        if out:
            printers['wmic_printers'] = out
    elif os_type == 'linux':
        out, _, _ = run_command("lpstat -t")
        if out:
            printers['lpstat'] = out
        if command_exists('cups'):
            out, _, _ = run_command("cupsctl -v")
            if out:
                printers['cups_settings'] = out
        if os.path.isdir('/etc/cups/ppd'):
            printers['cups_ppd_files'] = os.listdir('/etc/cups/ppd')[:50]
    elif os_type == 'macos':
        out, _, _ = run_command("lpstat -t")
        if out:
            printers['lpstat'] = out
    return printers

def get_bluetooth_devices() -> Dict[str, Any]:
    bt = {}
    os_type = get_os()
    if os_type == 'windows':
        ps = run_powershell("Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | Select-Object FriendlyName, Status, InstanceId | ConvertTo-Json")
        if ps:
            try:
                bt['bluetooth_devices'] = json.loads(ps)
            except:
                bt['bluetooth_raw'] = ps
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices")
            devices = []
            i = 0
            while True:
                try:
                    dev = winreg.EnumKey(key, i)
                    devices.append(dev)
                    i += 1
                except OSError:
                    break
            key.Close()
            if devices:
                bt['registry_paired_macs'] = devices
        except:
            pass
    elif os_type == 'linux':
        if command_exists('bluetoothctl'):
            out, _, _ = run_command("bluetoothctl paired-devices")
            if out:
                bt['bluetoothctl_paired'] = out
            out, _, _ = run_command("bluetoothctl devices")
            if out:
                bt['bluetoothctl_all'] = out
        if os.path.isdir('/var/lib/bluetooth'):
            bt['bt_lib_folder'] = os.listdir('/var/lib/bluetooth')[:20]
    elif os_type == 'macos':
        out, _, _ = run_command("system_profiler SPBluetoothDataType")
        if out:
            bt['system_profiler_bt'] = out
    return bt

def get_shadow_copies() -> Dict[str, Any]:
    shadows = {}
    os_type = get_os()
    if os_type == 'windows':
        out, _, _ = run_command("vssadmin list shadows")
        if out:
            shadows['vssadmin_list'] = out
        out, _, _ = run_command("vssadmin list shadowstorage")
        if out:
            shadows['vssadmin_storage'] = out
        ps = run_powershell("Get-CimInstance Win32_ShadowCopy -ErrorAction SilentlyContinue | Select-Object ID, VolumeName, InstallDate | ConvertTo-Json")
        if ps:
            shadows['cim_shadow_copies'] = ps
    elif os_type == 'linux':
        if command_exists('btrfs'):
            out, _, _ = run_command("btrfs subvolume list /")
            if out:
                shadows['btrfs_snapshots'] = out
        out, _, _ = run_command("lvs")
        if out:
            shadows['lvm_snapshots'] = out
        if command_exists('zfs'):
            out, _, _ = run_command("zfs list -t snapshot")
            if out:
                shadows['zfs_snapshots'] = out
    return shadows

def get_proxy_settings() -> Dict[str, Any]:
    proxy = {}
    os_type = get_os()
    if os_type == 'windows':
        out, _, _ = run_command("reg query \"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings\" | findstr Proxy")
        if out:
            proxy['registry_proxy'] = out
        ps = run_powershell("Get-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings' -ErrorAction SilentlyContinue | Select-Object ProxyEnable, ProxyServer, ProxyOverride | ConvertTo-Json")
        if ps:
            proxy['powershell_proxy'] = ps
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
            pac = winreg.QueryValueEx(key, "AutoConfigURL")[0]
            if pac:
                proxy['pac_url'] = pac
            winreg.CloseKey(key)
        except:
            pass
    elif os_type == 'linux':
        for var in ['http_proxy', 'https_proxy', 'ftp_proxy', 'all_proxy']:
            val = os.environ.get(var)
            if val:
                proxy[f'environ_{var}'] = val
        if command_exists('gsettings'):
            out, _, _ = run_command("gsettings get org.gnome.system.proxy mode")
            if out:
                proxy['gnome_proxy_mode'] = out
            out, _, _ = run_command("gsettings get org.gnome.system.proxy http")
            if out:
                proxy['gnome_http_proxy'] = out
        envfile = read_file_if_exists('/etc/environment')
        if envfile:
            proxy['etc_environment'] = [l for l in envfile.splitlines() if 'proxy' in l.lower()]
    elif os_type == 'macos':
        out, _, _ = run_command("networksetup -getwebproxy Wi-Fi")
        if out:
            proxy['macos_webproxy'] = out
        out, _, _ = run_command("networksetup -getsecurewebproxy Wi-Fi")
        if out:
            proxy['macos_secureproxy'] = out
    return proxy

# ==========================================================================
# SECCIÓN 5: RED, USUARIOS Y LOGS (ya estables)
# ==========================================================================

def get_network_info() -> Dict[str, Any]:
    net = {}
    if HAS_PSUTIL:
        net['interfaces'] = {}
        for iface, addrs in psutil.net_if_addrs().items():
            net['interfaces'][iface] = [{'address': addr.address, 'netmask': addr.netmask, 'family': str(addr.family)} for addr in addrs]
        net['stats'] = {iface: {'bytes_sent': s.bytes_sent, 'bytes_recv': s.bytes_recv, 'packets_sent': s.packets_sent, 'packets_recv': s.packets_recv} for iface, s in psutil.net_if_stats().items()}
        net['connections'] = []
        for conn in psutil.net_connections(kind='inet'):
            net['connections'].append({
                'fd': conn.fd,
                'family': conn.family,
                'type': conn.type,
                'laddr': conn.laddr,
                'raddr': conn.raddr,
                'status': conn.status,
                'pid': conn.pid
            })
    os_type = get_os()
    if os_type == 'linux':
        out, _, _ = run_command('ip route show table all')
        if out:
            net['routes'] = out
        dns = read_file_if_exists('/etc/resolv.conf')
        if dns:
            net['dns'] = dns
        hosts = read_file_if_exists('/etc/hosts')
        if hosts:
            net['hosts'] = hosts
    elif os_type == 'windows':
        out, _, _ = run_command('route print')
        if out:
            net['routes'] = out
        out, _, _ = run_command('ipconfig /all')
        if out:
            net['ipconfig'] = out
        ps = run_powershell("Get-DnsClientServerAddress -ErrorAction SilentlyContinue | Select-Object InterfaceAlias, ServerAddresses | ConvertTo-Json")
        if ps:
            try:
                net['dns_powershell'] = json.loads(ps)
            except:
                net['dns_powershell_raw'] = ps
    elif os_type == 'macos':
        out, _, _ = run_command('netstat -rn')
        if out:
            net['routes'] = out
        out, _, _ = run_command('scutil --dns')
        if out:
            net['dns'] = out
    return net

def get_users_info() -> Dict[str, Any]:
    users_info = {}
    os_type = get_os()
    if os_type == 'linux':
        passwd = read_file_if_exists('/etc/passwd')
        if passwd:
            users_info['passwd'] = passwd
        group = read_file_if_exists('/etc/group')
        if group:
            users_info['group'] = group
        out, _, _ = run_command('last -n 50 2>/dev/null')
        if out:
            users_info['last_logins'] = out
        histories = {}
        for user in os.listdir('/home'):
            hist_file = f'/home/{user}/.bash_history'
            if os.path.isfile(hist_file):
                content = read_file_if_exists(hist_file)
                if content:
                    histories[user] = content.splitlines()[-100:]
        if histories:
            users_info['command_history'] = histories
        out, _, _ = run_command('who')
        if out:
            users_info['current_who'] = out
        out, _, _ = run_command('ps aux')
        if out:
            users_info['ps_aux'] = out
    elif os_type == 'windows':
        out, _, _ = run_command('net user')
        if out:
            users_info['net_user'] = out
        out, _, _ = run_command('wmic useraccount get name, sid, status /format:csv')
        if out:
            users_info['wmic_useraccount'] = out
        out, _, _ = run_command('net localgroup')
        if out:
            users_info['net_localgroup'] = out
        ps = run_powershell("Get-EventLog -LogName Security -InstanceId 4624 -Newest 50 -ErrorAction SilentlyContinue | Select-Object TimeGenerated, ReplacementStrings | ConvertTo-Json")
        if ps:
            users_info['security_logons'] = ps
    elif os_type == 'macos':
        dscl = read_file_if_exists('/var/db/dslocal/nodes/Default/users')
        if dscl:
            users_info['dscl_users'] = dscl
        out, _, _ = run_command('last -n 50')
        if out:
            users_info['last_logins'] = out
        out, _, _ = run_command('who')
        if out:
            users_info['current_who'] = out
    return users_info

def get_logs_info() -> Dict[str, Any]:
    logs = {}
    os_type = get_os()
    if os_type == 'linux':
        log_files = ['syslog', 'auth.log', 'dmesg', 'kern.log', 'dpkg.log', 'apt/history.log', 'messages']
        for f in log_files:
            path = f'/var/log/{f}'
            content = read_file_if_exists(path)
            if content:
                logs[f] = content.splitlines()[-200:]
        if command_exists('journalctl'):
            out, _, _ = run_command('journalctl -n 100 --no-pager')
            if out:
                logs['journalctl'] = out
    elif os_type == 'windows':
        logs['system'] = run_powershell("Get-EventLog -LogName System -Newest 100 -ErrorAction SilentlyContinue | Select-Object TimeGenerated, EntryType, Source, Message | ConvertTo-Json")
        logs['application'] = run_powershell("Get-EventLog -LogName Application -Newest 100 -ErrorAction SilentlyContinue | Select-Object TimeGenerated, EntryType, Source, Message | ConvertTo-Json")
        logs['security'] = run_powershell("Get-EventLog -LogName Security -Newest 100 -ErrorAction SilentlyContinue | Select-Object TimeGenerated, EntryType, Source, Message | ConvertTo-Json")
    elif os_type == 'macos':
        log_files = ['system.log', 'kernel.log', 'install.log']
        for f in log_files:
            path = f'/var/log/{f}'
            content = read_file_if_exists(path)
            if content:
                logs[f] = content.splitlines()[-200:]
        if command_exists('log'):
            out, _, _ = run_command('log show --last 1h --predicate "eventMessage contains" --info')
            if out:
                logs['log_show'] = out
    return logs

def get_time_info() -> Dict[str, Any]:
    time_info = {}
    time_info['current_datetime'] = datetime.now().isoformat()
    time_info['timezone'] = str(datetime.now().astimezone().tzinfo)
    if HAS_PSUTIL:
        time_info['uptime_seconds'] = psutil.boot_time()
        time_info['uptime_formatted'] = str(datetime.now() - datetime.fromtimestamp(psutil.boot_time()))
    os_type = get_os()
    if os_type == 'linux':
        out, _, _ = run_command('timedatectl')
        if out:
            time_info['timedatectl'] = out
        tz = read_file_if_exists('/etc/timezone')
        if tz:
            time_info['timezone_file'] = tz
    elif os_type == 'windows':
        out, _, _ = run_command('systeminfo | findstr /B /C:"System Boot Time"')
        if out:
            time_info['boot_time_windows'] = out
        out, _, _ = run_command('tzutil /g')
        if out:
            time_info['timezone_win'] = out
    return time_info

# ==========================================================================
# SECCIÓN 6: RECOPILACIÓN TOTAL Y ESCRITURA
# ==========================================================================

def gather_all_information(parallel: bool = True, tree_root: str = '.', tree_depth: int = 8) -> Dict[str, Any]:
    functions = [
        ('system', get_system_info),
        ('hardware', get_hardware_info),
        ('battery', get_battery_info),
        ('monitor', get_monitor_info),
        ('firewall', get_firewall_info),
        ('updates', get_updates_info),
        ('usb_history', get_usb_history),
        ('kernel_modules', get_kernel_modules),
        ('secureboot_tpm', get_secureboot_tpm),
        ('network_cache', get_network_cache),
        ('execution_artifacts', get_execution_artifacts),
        ('shell_histories', get_shell_histories),
        ('trust_relationships', get_trust_relationships),
        ('containers_vms', get_containers_vms),
        ('encryption', get_encryption_status),
        ('recent_documents', get_recent_documents),
        ('stealth_persistence', get_stealth_persistence),
        ('browser_metadata', get_browser_metadata),
        ('security_policies', get_security_policies),
        ('ipc_artifacts', get_ipc_artifacts),
        ('crash_dumps', get_crash_dumps),
        ('system_file_timestamps', get_system_file_timestamps),
        ('wifi_profiles', get_wifi_profiles),
        ('network_mounts', get_network_mounts),
        ('certificates', get_installed_certificates),
        ('printers', get_printers_info),
        ('bluetooth', get_bluetooth_devices),
        ('shadow_copies', get_shadow_copies),
        ('proxy_settings', get_proxy_settings),
        ('network', get_network_info),
        ('users', get_users_info),
        ('logs', get_logs_info),
        ('time', get_time_info),
        ('packages', get_complete_package_list),
    ]
    result = {}
    if parallel and len(functions) > 1:
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_key = {executor.submit(func): key for key, func in functions}
            if HAS_TQDM:
                pbar = tqdm(total=len(functions), desc="Recopilando información", unit="módulo")
            for future in as_completed(future_to_key):
                key = future_to_key[future]
                try:
                    result[key] = future.result()
                except Exception as e:
                    result[key] = {'error': str(e)}
                if HAS_TQDM:
                    pbar.update(1)
            if HAS_TQDM:
                pbar.close()
    else:
        for key, func in functions:
            try:
                result[key] = func()
            except Exception as e:
                result[key] = {'error': str(e)}
    # Árbol de directorios (se ejecuta al final, no en paralelo)
    logger.info(colored(f"Generando árbol de directorios de {tree_root} (profundidad {tree_depth})...", Colors.CYAN))
    result['directory_tree'] = {
        'root': os.path.abspath(tree_root),
        'tree': generate_directory_tree(tree_root, show_hidden=True, max_depth=tree_depth)
    }
    return result

# ─── Funciones de escritura ──────────────────────────────────────────────

def write_output_json(data: Dict, output_file: str):
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

def write_output_md(data: Dict, output_file: str):
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# 🔍 Inventario Forense Completo\n\n")
        f.write(f"**Generado:** {data.get('metadata', {}).get('generated', '')}  \n")
        f.write(f"**Sistema:** {data.get('metadata', {}).get('system', '')}  \n")
        f.write(f"**Usuario:** {data.get('metadata', {}).get('user', '')}  \n\n")
        if 'directory_tree' in data:
            f.write("## 🌳 Árbol de directorios\n\n")
            f.write("```\n")
            f.write(data['directory_tree']['tree'])
            f.write("\n```\n\n")
        for section, content in data.items():
            if section in ['metadata', 'directory_tree']:
                continue
            f.write(f"## 📌 {section.capitalize()}\n\n")
            f.write("```json\n")
            f.write(json.dumps(content, indent=2, ensure_ascii=False, default=str))
            f.write("\n```\n\n")

def write_output_txt(data: Dict, output_file: str):
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("INVENTARIO FORENSE\n")
        f.write(f"Generado: {data.get('metadata', {}).get('generated', '')}\n")
        f.write(f"Sistema: {data.get('metadata', {}).get('system', '')}\n\n")
        if 'directory_tree' in data:
            f.write("=== ÁRBOL DE DIRECTORIOS ===\n")
            f.write(data['directory_tree']['tree'])
            f.write("\n\n")
        for section, content in data.items():
            if section in ['metadata', 'directory_tree']:
                continue
            f.write(f"=== {section.upper()} ===\n")
            f.write(json.dumps(content, indent=2, ensure_ascii=False, default=str))
            f.write("\n\n")

def write_output_xml(data: Dict, output_file: str):
    import xml.etree.ElementTree as ET
    root = ET.Element("forensic_inventory")
    for section, content in data.items():
        section_elem = ET.SubElement(root, section)
        try:
            json_str = json.dumps(content, ensure_ascii=False, default=str)
            section_elem.text = json_str
        except:
            section_elem.text = str(content)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(output_file, encoding='utf-8', xml_declaration=True)

def write_output_stats(data: Dict, output_file: str):
    stats = {
        'total_sections': len(data) - 2,
        'size_json': sys.getsizeof(data),
        'generated': data.get('metadata', {}).get('generated', '')
    }
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2)

# ─── CLI e interactivo ────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Inventario forense completo del sistema + árbol de directorios")
    parser.add_argument("--format", "-f", choices=["json", "md", "txt", "xml", "stats"], default="json",
                        help="Formato de salida")
    parser.add_argument("--output", "-o", help="Archivo de salida (sin extensión)")
    parser.add_argument("--tree-root", "-t", default=".", help="Directorio raíz para el árbol (ej. / o C:\\)")
    parser.add_argument("--tree-depth", type=int, default=8, help="Profundidad máxima del árbol")
    parser.add_argument("--quiet", "-q", action="store_true", help="Modo silencioso")
    parser.add_argument("--no-parallel", action="store_true", help="Deshabilitar paralelismo")
    return parser.parse_args()

def interactive_config():
    print(colored("\n=== Inventario Forense + Árbol de Directorios ===", Colors.HEADER))
    fmt = input(colored("Formato de salida [json]: ", Colors.CYAN)).strip().lower() or "json"
    out_base = input(colored("Nombre base del archivo [forensic_inventory]: ", Colors.CYAN)).strip() or "forensic_inventory"
    tree_root = input(colored("Directorio raíz para el árbol (./C:/) [.]: ", Colors.CYAN)).strip() or "."
    try:
        depth = int(input(colored("Profundidad máxima del árbol [8]: ", Colors.CYAN)).strip() or "8")
    except:
        depth = 8
    parallel = input(colored("¿Ejecutar en paralelo? (s/n) [s]: ", Colors.CYAN)).strip().lower() != "n"
    return {"format": fmt, "output_base": out_base, "tree_root": tree_root, "tree_depth": depth, "parallel": parallel}

# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    if args.quiet and not args.format:
        config = {"format": "json", "output_base": args.output or "forensic_inventory",
                  "tree_root": args.tree_root, "tree_depth": args.tree_depth,
                  "parallel": not args.no_parallel}
    elif not args.quiet and not args.format:
        config = interactive_config()
    else:
        config = {"format": args.format, "output_base": args.output or "forensic_inventory",
                  "tree_root": args.tree_root, "tree_depth": args.tree_depth,
                  "parallel": not args.no_parallel}

    logger.info(colored("Iniciando recopilación de información...", Colors.CYAN))
    data = gather_all_information(parallel=config["parallel"], tree_root=config["tree_root"], tree_depth=config["tree_depth"])

    data['metadata'] = {
        "generated": datetime.now().isoformat(),
        "system": platform.platform(),
        "user": getpass.getuser(),
        "cwd": os.getcwd(),
        "python_version": sys.version,
        "hostname": platform.node()
    }

    fmt = config["format"]
    out_base = config["output_base"]
    out_file = None
    if fmt == "json":
        out_file = f"{out_base}.json"
        write_output_json(data, out_file)
    elif fmt == "md":
        out_file = f"{out_base}.md"
        write_output_md(data, out_file)
    elif fmt == "txt":
        out_file = f"{out_base}.txt"
        write_output_txt(data, out_file)
    elif fmt == "xml":
        out_file = f"{out_base}.xml"
        write_output_xml(data, out_file)
    elif fmt == "stats":
        out_file = f"{out_base}_stats.json"
        write_output_stats(data, out_file)

    logger.info(colored(f"✅ Archivo generado: {out_file}", Colors.GREEN))

    print(colored("\n=== RESUMEN ===", Colors.BOLD))
    print(f"Secciones recopiladas: {len(data)-2}")
    print(f"Árbol de directorios: {config['tree_root']} (profundidad {config['tree_depth']})")
    print(f"Salida: {out_file}")
    print(f"Tamaño aprox: {sys.getsizeof(data) / 1024:.2f} KB")

if __name__ == '__main__':
    main()