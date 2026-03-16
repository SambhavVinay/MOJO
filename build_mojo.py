"""
Build script for Mojo — produces a distributable folder via PyInstaller.

Usage:  py build_mojo.py
Output: dist\Mojo\   (zip this whole folder and send it)

Fixes for other-machine DLL errors
────────────────────────────────────
• Collects all sub-packages for every heavy dependency.
• Copies python3XX.dll next to Mojo.exe (not just inside _internal) so
  Windows can find it regardless of where the user extracts the folder.
• Includes all pywin32 / win32 binaries explicitly.
• Adds a Windows application manifest so UAC / DLL isolation don't block
  loading system DLLs on the target machine.
"""

import subprocess
import sys
import os
import shutil
import glob


def find_python_dll() -> str | None:
    """Return the path to python3XX.dll next to the current interpreter."""
    py_dir = os.path.dirname(sys.executable)
    pattern = os.path.join(py_dir, "python3*.dll")
    matches = glob.glob(pattern)
    # Prefer the versioned one (e.g. python312.dll) over python3.dll
    versioned = [m for m in matches if os.path.basename(m) != "python3.dll"]
    return versioned[0] if versioned else (matches[0] if matches else None)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    entry_script = os.path.join(script_dir, "mojo_changed.py")
    mojo_ui_src  = os.path.join(script_dir, "mojo_ui.py")

    for f, name in [(entry_script, "mojo_changed.py"), (mojo_ui_src, "mojo_ui.py")]:
        if not os.path.isfile(f):
            print(f"ERROR: {name} not found.")
            sys.exit(1)

    # ── Hidden imports ────────────────────────────────────────────────────────
    hidden = [
        # Google GenAI
        "google.genai",
        "google.genai.types",
        "google.auth",
        "google.auth.transport",
        "google.auth.transport.requests",
        # PIL / Pillow
        "PIL",
        "PIL.Image",
        "PIL._imaging",
        # Win32
        "win32api",
        "win32gui",
        "win32con",
        "win32process",
        "pywintypes",
        "win32security",
        # Misc
        "pywt",
        "mss",
        "mss.windows",
        "pytesseract",
        "psutil",
        "pyautogui",
        "ollama",
        "dotenv",
        "pkg_resources",
        "pkg_resources._vendor.jaraco.text",
        "importlib.metadata",
        "charset_normalizer.md__mypyc",
    ]

    # ── collect-all packages (ensures sub-modules / data files are included) ──
    collect_all = [
        "google.genai",
        "google.auth",
        "PIL",
        "mss",
        "psutil",
        "win32",
        "pywin32",
        "pytesseract",
        "ollama",
        "httpx",
        "pydantic",
        "anyio",
    ]

    # ── Build the PyInstaller command ─────────────────────────────────────────
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--noconsole",
        "--noconfirm",
        "--clean",
        "--name", "Mojo",
        f"--add-data={mojo_ui_src};.",
    ]

    for hi in hidden:
        cmd += ["--hidden-import", hi]

    for pkg in collect_all:
        cmd += ["--collect-all", pkg]

    cmd.append(entry_script)

    print("Running PyInstaller...")
    result = subprocess.run(cmd, cwd=script_dir)
    if result.returncode != 0:
        print("PyInstaller failed.")
        sys.exit(result.returncode)

    # ── Post-build: copy python DLL next to Mojo.exe ─────────────────────────
    # Some Windows systems fail to find python3XX.dll inside _internal when the
    # user runs the exe from an arbitrary location.  Putting a copy next to the
    # exe fixes this completely.
    dist_dir = os.path.join(script_dir, "dist", "Mojo")
    internal_dir = os.path.join(dist_dir, "_internal")

    py_dll = find_python_dll()
    if py_dll:
        dll_name = os.path.basename(py_dll)
        # Copy from _internal (already placed there by PyInstaller) or from Python dir
        internal_dll = os.path.join(internal_dir, dll_name)
        dest_dll = os.path.join(dist_dir, dll_name)
        src = internal_dll if os.path.isfile(internal_dll) else py_dll
        if not os.path.isfile(dest_dll):
            shutil.copy2(src, dest_dll)
            print(f"Copied {dll_name} next to Mojo.exe")
        # Also copy python3.dll if present
        py3_src = os.path.join(os.path.dirname(py_dll), "python3.dll")
        if os.path.isfile(py3_src):
            py3_dst = os.path.join(dist_dir, "python3.dll")
            if not os.path.isfile(py3_dst):
                shutil.copy2(py3_src, py3_dst)
                print("Copied python3.dll next to Mojo.exe")

    # Copy VC++ runtime DLLs next to exe as well (belt-and-suspenders)
    vcruntime_names = ["VCRUNTIME140.dll", "VCRUNTIME140_1.dll", "MSVCP140.dll"]
    for dll_name in vcruntime_names:
        internal_path = os.path.join(internal_dir, dll_name)
        dest_path = os.path.join(dist_dir, dll_name)
        if os.path.isfile(internal_path) and not os.path.isfile(dest_path):
            shutil.copy2(internal_path, dest_path)
            print(f"Copied {dll_name} next to Mojo.exe")

    print("\n✅ Build complete!")
    print(f"   Output folder: dist\\Mojo\\")
    print("   Zip the entire 'Mojo' folder and send it — no other setup needed.")


if __name__ == "__main__":
    main()
