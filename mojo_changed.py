import tkinter as tk
import threading
import mss
import ollama
import time
import subprocess
import pyautogui
import win32gui
import win32process
import psutil
import win32con
import pytesseract
from PIL import Image

from mojo_ui import MojoUI 

# --- CONFIGURATION ---
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
USER_GOAL = "Software Development, Python Coding, and AI Research, General Productivity, Note Taking, Time Management, "

WHITELISTED_EXES = ["powershell.exe", "pwsh.exe", "cmd.exe", "code.exe", "cursor.exe", "python.exe", "pycharm64.exe", "SearchHost.exe", "WhatsApp.exe", "obs64.exe", "WindowsTerminal.exe"]
WHITELISTED_TITLES = ["gemini", "chatgpt", "github", "stackoverflow", "documentation", "localhost", "SearchHost", "visual studio code", "terminal"]

class MojoApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Mojo")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        self.bg_color = '#000001'
        self.root.config(bg=self.bg_color)
        self.root.attributes("-transparentcolor", self.bg_color)
        self.root.geometry("250x250+1300+700")

        self._offsetx = 0
        self._offsety = 0
        self.root.bind('<Button-1>', self.start_drag)
        self.root.bind('<B1-Motion>', self.on_drag)

        self.ui = MojoUI(self.root, self.bg_color)

        self.is_interrogating = False
        self.grace_period_until = 0
        self.control_panel = None 

        print("--- MOJO INITIALIZED ---")
        print(f"Goal: {USER_GOAL}\n")

        self.monitor_thread = threading.Thread(target=self.vision_loop, daemon=True)
        self.monitor_thread.start()

        self.refresh_topmost()
        self.root.mainloop()

    def start_drag(self, event):
        self._offsetx = event.x
        self._offsety = event.y

    def on_drag(self, event):
        x = self.root.winfo_x() + event.x - self._offsetx
        y = self.root.winfo_y() + event.y - self._offsety
        self.root.geometry(f"+{x}+{y}")
        self.ui.reposition_bubbles()

    def refresh_topmost(self):
        self.root.attributes("-topmost", True)
        self.root.lift()
        self.root.after(3000, self.refresh_topmost)

    def get_active_app_info(self):
        try:
            hwnd = win32gui.GetForegroundWindow()
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(pid)
            return process.name()
        except: return None

    def get_active_window_title(self):
        try: return win32gui.GetWindowText(win32gui.GetForegroundWindow())
        except: return ""

    def get_screen_data(self):
        with mss.mss() as sct:
            sct.shot(output="temp_screen.png")
            img = Image.open("temp_screen.png")
            width, height = img.size
            
            # Focused Crop: Focus on the top 500px (Tabs/URL) and center
            # This prevents AI from seeing background windows.
            focused_area = img.crop((0, 0, width, 600)) 
            focused_area.save("vision_input.png")

            tab_area = img.crop((0, 0, width, 80))
            try:
                tab_text = pytesseract.image_to_string(tab_area).strip()
            except:
                tab_text = ""
            return tab_text

    def vision_loop(self):
        while True:
            if self.is_interrogating:
                time.sleep(1)
                continue

            if time.time() < self.grace_period_until:
                rem = int(self.grace_period_until - time.time())
                self.update_ui("⏳", f"GRACE ({rem}s)", "cyan", "white")
                time.sleep(2)
                continue

            current_title = self.get_active_window_title()
            current_exe = self.get_active_app_info()
            current_hwnd = win32gui.GetForegroundWindow()
            tab_titles = self.get_screen_data()

            low_title = current_title.lower()
            exe_low = current_exe.lower() if current_exe else ""
            
            print("-" * 30)
            print(f"APP: {current_exe} | WINDOW: {current_title}")

            if exe_low in WHITELISTED_EXES or any(wt in low_title for wt in WHITELISTED_TITLES):
                print("DECISION: PRODUCTIVE (Whitelisted ✅)")
                self.update_ui("🔥", "LOCKED IN", "lime", "white")
                time.sleep(3)
                continue

            ignored = ["mojo", "tk", "explorer.exe", "task manager", "settings", "search host", "searchhost"]
            if any(x in low_title for x in ignored) or exe_low in ignored:
                print("DECISION: IGNORED (System ⚙️)")
                time.sleep(1)
                continue

            print("DECISION: EVALUATING WITH AI...")
            prompt = (
                f"SYSTEM: You are a strict productivity monitor. Focus ONLY on the ACTIVE window.\n"
                f"USER GOAL: {USER_GOAL}\n"
                f"ACTIVE WINDOW TITLE: {current_title}\n"
                f"VISIBLE TAB TEXT: {tab_titles[:150]}\n\n"
                f"RULES:\n"
                f"1. If the window is a browser, judge ONLY by the active tab/URL content.\n"
                f"2. Email, Netflix, Social Media, and Games are DISTRACTED.\n"
                f"3. Coding, AI Research, and Documentation are PRODUCTIVE.\n"
                f"OUTPUT: 'REASON: <1 sentence> | STATUS: <PRODUCTIVE/DISTRACTED>'"
            )

            try:
                response = ollama.chat(model='llava', messages=[{'role': 'user', 'content': prompt, 'images': ['vision_input.png']}], options={'temperature': 0})
                result = response['message']['content'].upper()
                print(f"AI ANALYSIS: {result.strip()}")

                if "STATUS: PRODUCTIVE" not in result:
                    print(f"RESULT: DISTRACTED 🚫")
                    self.update_ui("🚫", "DISTRACTED", "red", "red")
                    self.interrogate(current_exe, current_hwnd)
                else:
                    print("RESULT: PRODUCTIVE 🔥")
                    self.update_ui("🔥", "LOCKED IN", "lime", "white")
            except Exception as e:
                print(f"LLM Error: {e}")

            time.sleep(2)

    def update_ui(self, icon, text, icon_color, text_color):
        self.ui.update_state(text)

    def force_close_distractions(self, exe_name, target_hwnd):
        try:
            if not target_hwnd or not win32gui.IsWindow(target_hwnd): return
            print(f"FORCING CLOSE: {exe_name}")
            browsers = ["chrome.exe", "msedge.exe", "brave.exe", "firefox.exe"]
            if exe_name and exe_name.lower() in browsers:
                win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(target_hwnd)
                time.sleep(0.1)
                pyautogui.hotkey("ctrl", "w")
            else:
                pid = win32process.GetWindowThreadProcessId(target_hwnd)[1]
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            print(f"Close failed: {e}")

    def interrogate(self, target_exe, target_hwnd):
        if self.is_interrogating: return
        self.is_interrogating = True
        self.root.after(100, lambda: self._show_interrogate_dialog(target_exe, target_hwnd))

    def _show_interrogate_dialog(self, target_exe, target_hwnd):
        self.control_panel = tk.Toplevel(self.root)
        self.control_panel.overrideredirect(True)
        self.control_panel.attributes("-topmost", True)
        self.control_panel.geometry("300x60+1300+630") 
        self.control_panel.config(bg="#1a1a1a")

        def cleanup():
            # 1. Kill button panel
            if self.control_panel: 
                try: self.control_panel.destroy()
                except: pass
                self.control_panel = None
            
            # 2. Kill MojoUI chat
            if hasattr(self.ui, 'close_interrogation_dialog'):
                try: self.ui.close_interrogation_dialog()
                except: pass
            
            # 3. Reset Flag
            self.is_interrogating = False
            self.update_ui("🔥", "LOCKED IN", "lime", "white")
            print("CLEANUP: All interrogation windows closed.")

        def give_grace():
            print("USER ACTION: GRACE PERIOD GRANTED")
            self.grace_period_until = time.time() + 60
            cleanup()

        def force_kill():
            print(f"USER ACTION: KILLING {target_exe}")
            self.force_close_distractions(target_exe, target_hwnd)
            cleanup()

        def poll_target_window():
            if not self.is_interrogating:
                return
            try:
                window_still_open = bool(target_hwnd) and win32gui.IsWindow(target_hwnd)
            except Exception:
                window_still_open = False

            if not window_still_open:
                print("TARGET WINDOW CLOSED: Auto-closing interrogation/chat UI.")
                cleanup()
                return

            self.root.after(1000, poll_target_window)

        tk.Button(self.control_panel, text="Wait! 1m Grace", command=give_grace, bg="cyan", fg="black", font=("Arial", 10, "bold")).pack(side="left", expand=True, fill="both", padx=2, pady=2)
        tk.Button(self.control_panel, text=f"Kill {target_exe}", command=force_kill, bg="red", fg="white", font=("Arial", 10, "bold")).pack(side="right", expand=True, fill="both", padx=2, pady=2)

        try:
            self.ui.show_interrogation_dialog(
                target_exe, target_hwnd,
                on_valid_reason=lambda r: give_grace(),
                on_invalid=lambda e, h: force_kill(),
                on_close=cleanup
            )
        except Exception as e:
            print(f"UI Launch Error: {e}")
            cleanup()

        # Start watching for the user manually closing the distracted app/tab.
        self.root.after(1000, poll_target_window)

if __name__ == "__main__":
    MojoApp()