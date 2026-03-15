"""
Build script for Mojo — runs PyInstaller to produce a distributable folder.
Usage: python build_mojo.py
"""
import subprocess
import sys
import os

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    entry_script = os.path.join(script_dir, "mojo_changed.py")
    mojo_ui_src = os.path.join(script_dir, "mojo_ui.py")

    if not os.path.isfile(entry_script):
        print("ERROR: mojo_changed.py not found.")
        sys.exit(1)
    if not os.path.isfile(mojo_ui_src):
        print("ERROR: mojo_ui.py not found.")
        sys.exit(1)

    # Windows: use semicolon in --add-data (source;dest)
    add_data = f"{mojo_ui_src};."
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--noconsole",
        "--noconfirm",
        "--name", "Mojo",
        f"--add-data={add_data}",
        "--hidden-import", "google.genai",
        "--hidden-import", "PIL",
        "--hidden-import", "pywt",
        "--clean",
        entry_script,
    ]

    print("Running PyInstaller...")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=script_dir)
    if result.returncode != 0:
        print("PyInstaller failed.")
        sys.exit(result.returncode)
    print("Build complete. Output: dist\\Mojo\\")

if __name__ == "__main__":
    main()
