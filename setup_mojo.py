import os
import sys
import subprocess
import urllib.request
import tkinter as tk
from tkinter import messagebox
import ssl

# The absolute most reliable, official installer for Windows
TESSERACT_INSTALLER_URL = "https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe"

def check_tesseract_installed():
    """Check if Tesseract is installed in common locations or accessible in PATH."""
    common_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"C:\Users\Sambhav\Desktop\Mojo - Copy\Tesseract-OCR\tesseract.exe"
    ]
    
    # Check if bundled right next to us
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
    bundled_path = os.path.join(base_dir, "Tesseract-OCR", "tesseract.exe")
    if os.path.exists(bundled_path):
        return True

    for p in common_paths:
        if os.path.exists(p):
            return True

    # Check PATH
    try:
        subprocess.run(["tesseract", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return False

def download_installer(window, progress_var, status_var):
    installer_path = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "tesseract-setup.exe")
    os.makedirs(os.path.dirname(installer_path), exist_ok=True)
    
    status_var.set("Downloading Tesseract OCR Installer...\nThis might take a minute.")
    window.update()
    
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        req = urllib.request.Request(TESSERACT_INSTALLER_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ctx) as response:
            total_size = int(response.getheader('Content-Length').strip())
            downloaded = 0
            chunk_size = 8192
            
            with open(installer_path, 'wb') as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = int((downloaded / total_size) * 100)
                        progress_var.set(percent)
                        status_var.set(f"Downloading... {percent}%")
                        window.update()
                        
        return installer_path
    except Exception as e:
        messagebox.showerror("Download Error", f"Failed to download Tesseract: {e}")
        return None

def launch_mojo(window=None):
    if window:
        window.destroy()
        
    try:
        import mojo_changed
        # Re-run path setup so it finds the newly installed Tesseract without needing a restart
        mojo_changed._setup_tesseract_path()
        mojo_changed.MojoApp()
    except Exception as e:
        import traceback
        # Try to show a popup even if main UI fails
        try:
            tk.Tk().withdraw()
            messagebox.showerror("Crsh", f"Failed to start Mojo:\n{e}\n\n{traceback.format_exc()}")
        except:
            print(f"Failed to start Mojo: {e}")

def run_setup_ui():
    if check_tesseract_installed():
        # Everything is ready, just launch Mojo!
        launch_mojo()
        return

    # Tesseract is missing. Show setup UI.
    root = tk.Tk()
    root.title("Mojo Setup")
    root.geometry("450x250")
    root.eval("tk::PlaceWindow . center")
    root.resizable(False, False)
    root.configure(bg="#1e1e1e")

    tk.Label(
        root, 
        text="Welcome to Mojo! \U0001FA84", 
        font=("Segoe UI", 16, "bold"), 
        fg="white", bg="#1e1e1e"
    ).pack(pady=(20, 5))

    tk.Label(
        root, 
        text="We need to install the 'Tesseract OCR' engine so\nMojo can read your screen and keep you focused.", 
        font=("Segoe UI", 10), 
        fg="#aaaaaa", bg="#1e1e1e"
    ).pack(pady=(0, 20))

    progress_var = tk.IntVar()
    status_var = tk.StringVar(value="Ready to install.")

    status_lbl = tk.Label(root, textvariable=status_var, font=("Segoe UI", 9), fg="#cccccc", bg="#1e1e1e")
    status_lbl.pack()

    btn_frame = tk.Frame(root, bg="#1e1e1e")
    btn_frame.pack(pady=15)

    def start_install():
        btn_install.config(state="disabled")
        btn_skip.config(state="disabled")
        
        installer = download_installer(root, progress_var, status_var)
        
        if installer and os.path.exists(installer):
            status_var.set("Running the installer... Please click through it.")
            root.update()
            
            # Run the installer detached and wait
            def check_installer_done(proc, window_root):
                if proc.poll() is None:
                    window_root.after(1000, check_installer_done, proc, window_root)
                else:
                    status_var.set("Installation complete! Launching Mojo...")
                    window_root.update()
                    window_root.after(1500, lambda: launch_mojo(window_root))
            
            try:
                # Use Shell=True to ensure UAC prompts can appear
                proc = subprocess.Popen(installer, shell=True)
                root.after(1000, check_installer_done, proc, root)
            except Exception as e:
                messagebox.showerror("Install Failed", f"Could not launch installer: {e}")
                btn_install.config(state="normal")
                btn_skip.config(state="normal")
                status_var.set("Ready to install.")
        else:
            btn_install.config(state="normal")
            btn_skip.config(state="normal")
            status_var.set("Failed to download installer.")

    btn_install = tk.Button(btn_frame, text="Download & Install OCR Engine", bg="#06b6d4", fg="white", font=("Segoe UI", 10, "bold"), padx=10, pady=5, relief="flat", command=start_install)
    btn_install.pack(side="left", padx=10)

    btn_skip = tk.Button(btn_frame, text="Skip for Now (Errors may occur)", bg="#444444", fg="white", font=("Segoe UI", 9), padx=10, pady=5, relief="flat", command=lambda: launch_mojo(root))
    btn_skip.pack(side="left", padx=10)

    root.mainloop()

if __name__ == "__main__":
    run_setup_ui()
