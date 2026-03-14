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
from PIL import Image          # ImageTk removed — no longer needed

from mojo_ui import MojoUI    # ← only new import

# --- CONFIGURATION ---
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
USER_GOAL = "Software Development, Python Coding, and AI Research, General Productivity, Note Taking, Time Management, "

WHITELISTED_EXES = ["powershell.exe", "cmd.exe", "code.exe", "cursor.exe", "python.exe", "pycharm64.exe","SearchHost.exe","WhatsApp.exe","obs64.exe"]
WHITELISTED_TITLES = ["gemini", "chatgpt", "github", "stackoverflow", "documentation", "localhost", "SearchHost"]

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

        # ── UI: replaces old orb image + status_label + text_label ──
        self.ui = MojoUI(self.root, self.bg_color)   # ← NEW

        self.is_interrogating = False
        self.grace_period_until = 0
        self.dialog_win = None

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
        self.ui.reposition_bubbles()   # ← NEW: bubbles follow orb

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
            tab_area = img.crop((0, 0, width, 80))

            try:
                full_text = pytesseract.image_to_string(img).strip()
                tab_text = pytesseract.image_to_string(tab_area).strip()
            except:
                full_text = ""
                tab_text = ""

            img.thumbnail((800, 800))
            img.save("vision_input.png")
            return tab_text, full_text

    def vision_loop(self):
        while True:
            # Pause vision loop if we are currently handling a distraction
            if self.is_interrogating:
                time.sleep(1)
                continue

            if time.time() < self.grace_period_until:
                self.update_ui("⏳", "GRACE PERIOD", "cyan", "white")
                time.sleep(2)
                continue

            current_title = self.get_active_window_title()
            current_exe = self.get_active_app_info()
            current_hwnd = win32gui.GetForegroundWindow()

            tab_titles, screen_content = self.get_screen_data()

            # --- TERMINAL LOGGING ---
            print("-" * 50)
            print(f"[{time.strftime('%H:%M:%S')}] SCANNING...")
            print(f"ACTIVE WINDOW: {current_title} ({current_exe})")
            if tab_titles:
                print(f"DETECTED TABS: {tab_titles.replace(chr(10), ' | ')}")
            print("-" * 50)

            # --- STEP 1: HARD WHITELIST CHECK ---
            low_title = current_title.lower()
            is_productive_exe = current_exe and current_exe.lower() in WHITELISTED_EXES
            is_productive_title = any(wt in low_title for wt in WHITELISTED_TITLES)

            if is_productive_exe or is_productive_title:
                self.update_ui("🔥", "LOCKED IN", "lime", "white")
                time.sleep(3)
                continue

            # Skip system apps
            ignored = ["mojo", "tk", "explorer.exe", "task manager", "settings", "search host","WhatsApp","SearchHost"]
            if any(x in low_title for x in ignored) or (current_exe and current_exe.lower() in ignored):
                time.sleep(1)
                continue

            # --- STEP 2: LLM ANALYSIS ---
            prompt = f"""Identify if the user is distracted.
            USER GOAL: {USER_GOAL}
            ACTIVE WINDOW: {current_title}
            DETECTED TABS/TEXT: {tab_titles}
            
            Answer 'STATUS: PRODUCTIVE' if the window/tabs support the goal.
            Answer 'STATUS: DISTRACTED' if it is social media, shopping, or non-educational entertainment.
            
            ONLY reply with the STATUS line."""

            try:
                response = ollama.chat(
                    model='llava',
                    messages=[{'role': 'user', 'content': prompt, 'images': ['vision_input.png']}],
                    options={'temperature': 0}
                )
                raw = response['message']['content'].upper()

                if "PRODUCTIVE" in raw and "DISTRACTED" not in raw:
                    self.update_ui("🔥", "LOCKED IN", "lime", "white")
                else:
                    print(f"!!! DISTRACTION TRIGGERED !!! -> {current_title}")
                    self.update_ui("🚫", "DISTRACTED", "red", "red")
                    self.interrogate(current_exe, current_hwnd)

            except Exception as e:
                print(f"LLM Error: {e}")

            time.sleep(2)

    # ── UI update: forwards to MojoUI instead of old labels ──
    def update_ui(self, icon, text, icon_color, text_color):
        self.ui.update_state(text)   # ← NEW (replaces status_label + text_label)

    def force_close_distractions(self, exe_name, target_hwnd):
        try:
            if not target_hwnd or not win32gui.IsWindow(target_hwnd): return

            browsers = ["chrome.exe", "msedge.exe", "brave.exe", "firefox.exe"]
            if exe_name and exe_name.lower() in browsers:
                win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(target_hwnd)
                time.sleep(0.1)
                pyautogui.hotkey("ctrl", "w")
            else:
                subprocess.run(
                    ["taskkill", "/F", "/PID",
                     str(psutil.Process(win32process.GetWindowThreadProcessId(target_hwnd)[1]).pid)],
                    capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW
                )
        except Exception as e:
            print(f"Close failed: {e}")

    def interrogate(self, target_exe, target_hwnd):
        if self.is_interrogating: return
        self.is_interrogating = True
        self.root.after(100, lambda: self._show_interrogate_dialog(target_exe, target_hwnd))

    # ── Dialog: now a chat UI via MojoUI instead of the old form ──
    def _show_interrogate_dialog(self, target_exe, target_hwnd):

        def on_valid_reason(_reason):
            print("Reason accepted. Grace period granted.")
            self.grace_period_until = time.time() + 300   # ← same 300s as original
            return True

        def on_invalid(exe, hwnd):
            print(f"Reason rejected. Closing {exe}")
            self.force_close_distractions(exe, hwnd)

        def on_close():
            self.is_interrogating = False
            self.dialog_win = None
            self.update_ui("🔥", "LOCKED IN", "lime", "white")

        self.dialog_win = self.ui.show_interrogation_dialog(
            target_exe, target_hwnd,
            on_valid_reason=on_valid_reason,
            on_invalid=on_invalid,
            on_close=on_close,
        )

if __name__ == "__main__":
    MojoApp()