#!/usr/bin/env python3
"""
Generador interactivo de diferencias Git (todos los cambios, como GitHub Desktop)
Permite seleccionar qué archivos incluir en el informe.
"""

import os
import subprocess
import sys
import json
import xml.etree.ElementTree as ET
import platform
import getpass
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

# ─── Importar utilidades de context.py si existe ───────────────────────────
try:
    from context import (
        Colors, colored, format_size, compact_content, get_language,
        get_instance_dir, get_next_version, load_profile, save_profile,
        prompt_compact_mode, prompt_line_numbers, select_output_format,
        prompt_save_profile
    )
    HAS_CONTEXT = True
except ImportError:
    # Implementaciones mínimas
    class Colors:
        HEADER = '\033[95m'; BLUE = '\033[94m'; CYAN = '\033[96m'
        GREEN = '\033[92m'; WARNING = '\033[93m'; FAIL = '\033[91m'
        ENDC = '\033[0m'; BOLD = '\033[1m'; UNDERLINE = '\033[4m'
    def colored(text, color):
        return f"{color}{text}{Colors.ENDC}" if sys.stdout.isatty() else text
    def format_size(size_bytes):
        for unit in ['B','KB','MB','GB','TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f}PB"
    def compact_content(text):
        lines = text.splitlines()
        compacted = []
        prev_empty = False
        for line in lines:
            if line.strip() == '':
                if not prev_empty:
                    compacted.append('')
                    prev_empty = True
            else:
                compacted.append(line)
                prev_empty = False
        return '\n'.join(compacted)
    def get_instance_dir(caller_file):
        base = Path.cwd() / "context_generation"
        base.mkdir(exist_ok=True)
        return base
    def get_next_version(output_dir):
        max_v = 0
        for f in output_dir.glob("git_changes_*.md"):
            try:
                num = int(f.stem.split('_')[-1])
                if num > max_v: max_v = num
            except: pass
        return max_v + 1
    def load_profile():
        profile_path = Path.cwd() / ".git_changes_profile.json"
        if profile_path.exists():
            try:
                with open(profile_path, "r") as f:
                    return json.load(f)
            except: pass
        return None
    def save_profile(profile):
        try:
            with open(".git_changes_profile.json", "w") as f:
                json.dump(profile, f, indent=2)
            print(colored("Perfil guardado.", Colors.GREEN))
        except Exception as e:
            print(colored(f"No se pudo guardar perfil: {e}", Colors.WARNING))
    def prompt_compact_mode():
        resp = input(colored("¿Modo compacto (reducir espacios en blanco)? (s/n) [n]: ", Colors.CYAN)).strip().lower()
        return resp == 's' or resp == 'si'
    def prompt_line_numbers():
        resp = input(colored("¿Incluir números de línea? (s/n) [n]: ", Colors.CYAN)).strip().lower()
        return resp == 's' or resp == 'si'
    def select_output_format():
        print(colored("\nFormato de salida:", Colors.HEADER))
        print("1. Markdown (.md)")
        print("2. JSON (.json)")
        print("3. XML (.xml)")
        print("4. Texto plano (.txt)")
        print("5. Solo estadísticas (sin contenido de archivos)")
        print("6. Todos los formatos (md, json, xml, txt)")
        while True:
            choice = input(colored("Elige (1-6) [1]: ", Colors.CYAN)).strip()
            if choice in ('', '1'): return 'md'
            elif choice == '2': return 'json'
            elif choice == '3': return 'xml'
            elif choice == '4': return 'txt'
            elif choice == '5': return 'stats'
            elif choice == '6': return 'all'
            else: print(colored("Opción no válida.", Colors.WARNING))
    def prompt_save_profile():
        resp = input(colored("¿Guardar este perfil para futuras ejecuciones? (s/n) [n]: ", Colors.CYAN)).strip().lower()
        return resp == 's' or resp == 'si'
    language_map = {'.py':'Python','.js':'JavaScript','.md':'Markdown'}
    def get_language(ext, filename=None):
        return language_map.get(ext.lower(), 'Texto')
    HAS_CONTEXT = False

# ─── Configuración de logging ──────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('git_changes_selector')

# ─── Detección de cambios (como git status --porcelain) ───────────────────
def get_all_changes():
    """
    Detecta todos los cambios en el working directory respecto a HEAD.
    Retorna lista de dicts con: path, status (M, A, D, U, R, C, etc.), y old_path (si renombrado).
    """
    try:
        output = subprocess.check_output(
            ['git', 'status', '--porcelain'],
            stderr=subprocess.DEVNULL,
            text=True
        ).strip()
        if not output:
            return []
        changes = []
        for line in output.splitlines():
            if not line.strip():
                continue
            # Formato: XY path [-> old_path] (para renombrados)
            status_code = line[:2]
            rest = line[3:].strip()
            # Analizar estado
            x = status_code[0]  # staged
            y = status_code[1]  # unstaged / working tree
            # Determinar el estado principal (similar a GitHub Desktop)
            if y == 'M' or x == 'M':
                final_status = 'M'  # modified
            elif y == 'D' or x == 'D':
                final_status = 'D'  # deleted
            elif y == 'A' or x == 'A':
                final_status = 'A'  # added
            elif y == 'R' or x == 'R':
                final_status = 'R'  # renamed
                parts = rest.split(' -> ')
                path = parts[1] if len(parts) > 1 else rest
                old_path = parts[0] if len(parts) > 1 else None
                changes.append({'path': path, 'status': final_status, 'old_path': old_path})
                continue
            elif y == 'C' or x == 'C':
                final_status = 'C'  # copied
            elif y == '?' and x == '?':
                final_status = 'U'  # untracked
            elif y == '!' and x == '!':
                continue  # ignorado, no lo mostramos
            else:
                final_status = '?'  # otro
            changes.append({'path': rest, 'status': final_status})
        return changes
    except subprocess.CalledProcessError:
        logger.error(colored("Error: No estás en un repositorio Git.", Colors.FAIL))
        sys.exit(1)

def get_original_content_from_git(filepath):
    """Contenido en HEAD, o None si no existe."""
    try:
        return subprocess.check_output(
            ['git', 'show', f'HEAD:{filepath}'],
            stderr=subprocess.DEVNULL,
            text=True
        )
    except subprocess.CalledProcessError:
        return None

def read_current_content(filepath):
    """Lee el archivo actual del disco."""
    if not os.path.isfile(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception as e:
        return f"[Error leyendo archivo: {e}]"

# ─── Interfaz para seleccionar archivos ────────────────────────────────────
def select_files_interactively(changes):
    """Muestra lista de cambios y permite seleccionar cuáles incluir."""
    if not changes:
        return []
    print(colored("\n=== ARCHIVOS CON CAMBIOS ===", Colors.BOLD))
    for i, ch in enumerate(changes, 1):
        status_display = {
            'M': 'Modificado',
            'A': 'Agregado (staged)',
            'D': 'Eliminado',
            'U': 'Untracked (nuevo)',
            'R': 'Renombrado',
            'C': 'Copiado'
        }.get(ch['status'], ch['status'])
        extra = f" (de: {ch['old_path']})" if ch.get('old_path') else ""
        print(f"{i:2d}. [{status_display}] {ch['path']}{extra}")
    print("\nOpciones: 'all', 'none', o números separados por comas (ej. 1,3,5-7)")
    while True:
        sel = input(colored("Selecciona los archivos a incluir: ", Colors.CYAN)).strip().lower()
        if sel == 'all':
            return changes
        elif sel == 'none':
            return []
        else:
            selected_indices = set()
            try:
                parts = sel.split(',')
                for part in parts:
                    part = part.strip()
                    if '-' in part:
                        start, end = map(int, part.split('-'))
                        selected_indices.update(range(start, end+1))
                    else:
                        selected_indices.add(int(part))
                selected = [changes[i-1] for i in selected_indices if 1 <= i <= len(changes)]
                if selected:
                    return selected
            except ValueError:
                pass
            print(colored("Selección no válida, intente otra vez.", Colors.WARNING))

# ─── Generación de salida para diferencias ─────────────────────────────────
def generate_diff_text(original, modified, status, compact, line_numbers):
    if compact:
        if original: original = compact_content(original)
        if modified: modified = compact_content(modified)
    lines = []
    lines.append("### Versión ORIGINAL (HEAD)")
    if original is None:
        if status == 'U':
            lines.append("[Archivo nuevo (untracked) - no existe en HEAD]")
        elif status == 'A':
            lines.append("[Archivo agregado (staged) - no existe en HEAD]")
        else:
            lines.append("[Archivo no existe en HEAD]")
    elif original.strip() == "":
        lines.append("[Archivo vacío en HEAD]")
    else:
        if line_numbers:
            orig_lines = original.splitlines()
            lines.append('\n'.join(f"{i+1:4d}: {line}" for i, line in enumerate(orig_lines)))
        else:
            lines.append(original)
    lines.append("\n### Versión MODIFICADA (Working Directory)")
    if status == 'D':
        lines.append("[Archivo ELIMINADO en el Working Directory]")
    elif modified is None:
        lines.append("[Archivo no encontrado en Working Directory]")
    elif modified.strip() == "":
        lines.append("[Archivo vacío en el WD]")
    else:
        if line_numbers:
            mod_lines = modified.splitlines()
            lines.append('\n'.join(f"{i+1:4d}: {line}" for i, line in enumerate(mod_lines)))
        else:
            lines.append(modified)
    return '\n'.join(lines)

def write_markdown(output_dir, files_data, metadata, version, compact, line_numbers):
    out_file = output_dir / f'git_changes_{version:03d}.md'
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write("# CAMBIOS EN EL REPOSITORIO GIT\n\n")
        f.write(f"**Generado:** {metadata['generated']}  \n")
        f.write(f"**Sistema:** {metadata['system']}  \n")
        f.write(f"**Usuario:** {metadata['user']}  \n")
        f.write(f"**Directorio:** {metadata['root']}  \n\n")
        f.write("## Archivos seleccionados\n\n")
        for d in files_data:
            status_text = {
                'M':'Modificado', 'A':'Agregado (staged)', 'D':'Eliminado',
                'U':'Untracked (nuevo)', 'R':'Renombrado', 'C':'Copiado'
            }.get(d['status'], d['status'])
            f.write(f"### `{d['path']}` (Lenguaje: {d['language']}) - {status_text}\n\n")
            f.write(generate_diff_text(d['original'], d['modified'], d['status'], compact, line_numbers))
            f.write("\n\n---\n\n")
    return out_file

def write_json(output_dir, files_data, metadata, version):
    out_file = output_dir / f'git_changes_{version:03d}.json'
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump({'metadata': metadata, 'files': files_data}, f, indent=2, ensure_ascii=False)
    return out_file

def write_xml(output_dir, files_data, metadata, version):
    out_file = output_dir / f'git_changes_{version:03d}.xml'
    root = ET.Element('git_changes')
    meta = ET.SubElement(root, 'metadata')
    for k, v in metadata.items():
        ET.SubElement(meta, k).text = v
    files_elem = ET.SubElement(root, 'files')
    for d in files_data:
        fe = ET.SubElement(files_elem, 'file')
        ET.SubElement(fe, 'path').text = d['path']
        ET.SubElement(fe, 'status').text = d['status']
        ET.SubElement(fe, 'language').text = d['language']
        ET.SubElement(fe, 'original').text = d['original'] if d['original'] else ""
        ET.SubElement(fe, 'modified').text = d['modified'] if d['modified'] else ""
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(out_file, encoding='utf-8', xml_declaration=True)
    return out_file

def write_txt(output_dir, files_data, metadata, version):
    out_file = output_dir / f'git_changes_{version:03d}.txt'
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(f"CAMBIOS GIT\nGenerado: {metadata['generated']}\nSistema: {metadata['system']}\nUsuario: {metadata['user']}\nDirectorio: {metadata['root']}\n\n")
        for d in files_data:
            status_text = {
                'M':'Modificado', 'A':'Agregado', 'D':'Eliminado',
                'U':'Untracked', 'R':'Renombrado', 'C':'Copiado'
            }.get(d['status'], d['status'])
            f.write(f"ARCHIVO: {d['path']} ({d['language']}) - {status_text}\n{'='*60}\n")
            f.write(generate_diff_text(d['original'], d['modified'], d['status'], compact=False, line_numbers=False))
            f.write(f"\n{'='*60}\n\n")
    return out_file

def write_stats(output_dir, files_data, metadata, version):
    stats = compute_stats(files_data)
    out_file = output_dir / f'git_changes_stats_{version:03d}.json'
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump({'metadata': metadata, 'stats': stats}, f, indent=2, ensure_ascii=False)
    return out_file

def compute_stats(files_data):
    total = len(files_data)
    lang_counts = {}
    status_counts = {'M':0, 'A':0, 'D':0, 'U':0, 'R':0, 'C':0}
    total_orig_lines = 0
    total_mod_lines = 0
    total_orig_size = 0
    total_mod_size = 0
    for d in files_data:
        lang = d['language']
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
        status_counts[d['status']] = status_counts.get(d['status'], 0) + 1
        if d['original']:
            total_orig_lines += d['original'].count('\n')
            total_orig_size += len(d['original'].encode('utf-8'))
        if d['modified']:
            total_mod_lines += d['modified'].count('\n')
            total_mod_size += len(d['modified'].encode('utf-8'))
    return {
        'total_files': total,
        'status': status_counts,
        'original_lines': total_orig_lines,
        'modified_lines': total_mod_lines,
        'original_size': format_size(total_orig_size),
        'modified_size': format_size(total_mod_size),
        'languages': lang_counts
    }

def format_stats_md(stats):
    md = f"- **Archivos procesados:** {stats['total_files']}\n"
    md += f"  - Modificados: {stats['status'].get('M',0)}\n"
    md += f"  - Agregados (staged): {stats['status'].get('A',0)}\n"
    md += f"  - Eliminados: {stats['status'].get('D',0)}\n"
    md += f"  - Untracked: {stats['status'].get('U',0)}\n"
    md += f"  - Renombrados/Copiados: {stats['status'].get('R',0)+stats['status'].get('C',0)}\n"
    md += f"- **Líneas (original):** {stats['original_lines']}\n"
    md += f"- **Líneas (modificado):** {stats['modified_lines']}\n"
    md += f"- **Tamaño original:** {stats['original_size']}\n"
    md += f"- **Tamaño modificado:** {stats['modified_size']}\n"
    md += f"- **Lenguajes:** {', '.join(f'{k} ({v})' for k,v in sorted(stats['languages'].items(), key=lambda x: x[1], reverse=True))}\n"
    return md

# ─── Función principal ────────────────────────────────────────────────────
def main():
    if not os.path.isdir(".git"):
        logger.error(colored("No se encontró .git. Ejecuta en la raíz de un repositorio Git.", Colors.FAIL))
        sys.exit(1)

    # Detectar todos los cambios
    all_changes = get_all_changes()
    if not all_changes:
        logger.info(colored("No hay cambios detectados (working directory limpio).", Colors.GREEN))
        return

    # Mostrar resumen y seleccionar archivos
    print(colored(f"\nTotal de cambios detectados: {len(all_changes)}", Colors.CYAN))
    selected_changes = select_files_interactively(all_changes)
    if not selected_changes:
        logger.info(colored("No se seleccionó ningún archivo. Saliendo.", Colors.WARNING))
        return

    print(colored(f"\nArchivos seleccionados: {len(selected_changes)}", Colors.GREEN))

    # Cargar perfil o preguntar opciones
    profile = load_profile()
    if profile:
        output_format = profile.get('format', 'md')
        compact_flag = profile.get('compact', False)
        line_numbers = profile.get('line_numbers', False)
        print(colored("Perfil cargado.", Colors.GREEN))
    else:
        output_format = select_output_format()
        compact_flag = prompt_compact_mode()
        line_numbers = prompt_line_numbers() if output_format in ('md', 'all') else False
        profile = {'format': output_format, 'compact': compact_flag, 'line_numbers': line_numbers}
        if prompt_save_profile():
            save_profile(profile)

    # Preparar directorio de salida
    instance_dir = get_instance_dir(__file__)
    version = get_next_version(instance_dir)
    print(colored(f"Directorio de salida: {instance_dir} - Versión: {version:03d}", Colors.CYAN))

    # Obtener contenidos en paralelo
    files_data = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {}
        for ch in selected_changes:
            path = ch['path']
            status = ch['status']
            # Para eliminados, solo original; para untracked/agregados, solo current; para modificados, ambos
            if status == 'D':
                futures[executor.submit(get_original_content_from_git, path)] = (path, status, 'original')
            elif status in ('U', 'A', 'R', 'C'):
                # Estos no tienen original en HEAD (o es difícil de obtener si renombrado)
                # Para renombrados, el original estaría en old_path, pero simplificamos: no mostramos original
                futures[executor.submit(read_current_content, path)] = (path, status, 'current')
            else:  # M
                futures[executor.submit(get_original_content_from_git, path)] = (path, status, 'original')
                futures[executor.submit(read_current_content, path)] = (path, status, 'current')
        results = {}
        for future in as_completed(futures):
            path, status, kind = futures[future]
            if path not in results:
                results[path] = {'status': status}
            results[path][kind] = future.result()

    for path, data in results.items():
        status = data['status']
        original = data.get('original') if status in ('M', 'D') else None
        modified = data.get('current') if status != 'D' else None
        # Para renombrados, podríamos buscar el original, pero lo dejamos como None
        if status == 'R':
            original = None
        _, ext = os.path.splitext(path)
        lang = get_language(ext, os.path.basename(path))
        files_data.append({
            'path': path,
            'status': status,
            'language': lang,
            'original': original,
            'modified': modified
        })

    metadata = {
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'system': platform.platform(),
        'user': getpass.getuser(),
        'root': os.path.abspath('.')
    }

    # Generar salida
    generated_files = []
    if output_format == 'stats':
        out = write_stats(instance_dir, files_data, metadata, version)
        generated_files.append(str(out))
    elif output_format == 'all':
        generated_files.append(str(write_markdown(instance_dir, files_data, metadata, version, compact_flag, line_numbers)))
        generated_files.append(str(write_json(instance_dir, files_data, metadata, version)))
        generated_files.append(str(write_xml(instance_dir, files_data, metadata, version)))
        generated_files.append(str(write_txt(instance_dir, files_data, metadata, version)))
    elif output_format == 'md':
        generated_files.append(str(write_markdown(instance_dir, files_data, metadata, version, compact_flag, line_numbers)))
    elif output_format == 'json':
        generated_files.append(str(write_json(instance_dir, files_data, metadata, version)))
    elif output_format == 'xml':
        generated_files.append(str(write_xml(instance_dir, files_data, metadata, version)))
    elif output_format == 'txt':
        generated_files.append(str(write_txt(instance_dir, files_data, metadata, version)))

    # Estadísticas
    stats = compute_stats(files_data)
    print(colored("\n=== ESTADÍSTICAS FINALES ===", Colors.BOLD))
    print(format_stats_md(stats))
    print(colored(f"Archivos generados: {', '.join(generated_files)}", Colors.GREEN))

if __name__ == '__main__':
    main()