import tkinter as tk
import threading
import mss
import ollama
import time
from PIL import Image
import os
import subprocess
import pyautogui
import win32gui
import win32process
import psutil
import win32con

class MojoApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Mojo") 
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.geometry("250x150+1300+700") 
        self.root.config(bg='black')
        self.root.attributes("-alpha", 0.9)

        self.status_label = tk.Label(self.root, text="👁️", font=("Arial", 40), bg='black', fg='white')
        self.status_label.pack()
        
        self.text_label = tk.Label(self.root, text="System Online", font=("Arial", 10), bg='black', fg='white')
        self.text_label.pack()

        # State management
        self.is_interrogating = False
        self.grace_period_until = 0  
        self.dialog_win = None 

        self.monitor_thread = threading.Thread(target=self.vision_loop, daemon=True)
        self.monitor_thread.start()

        # Keep the window on top every 5 seconds
        self.refresh_topmost()
        self.root.mainloop()

    def refresh_topmost(self):
        """Ensures the window stays on top of everything else permanently."""
        self.root.attributes("-topmost", True)
        self.root.lift()
        self.root.after(5000, self.refresh_topmost)

    def get_active_app_info(self):
        try:
            hwnd = win32gui.GetForegroundWindow()
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(pid)
            return process.name()
        except:
            return None

    def get_active_window_title(self):
        try:
            return win32gui.GetWindowText(win32gui.GetForegroundWindow())
        except:
            return ""

    def take_optimized_screenshot(self):
        with mss.mss() as sct:
            sct.shot(output="screen.png")
            img = Image.open("screen.png")
            img.thumbnail((500, 500)) 
            img.save("screen_small.png")
    
    def force_close_distractions(self, exe_name):
        try:
            # SAFETY LIST: Never kill these
            protected_exes = ["python.exe", "explorer.exe", "taskmgr.exe"]
            if exe_name and exe_name.lower() in protected_exes:
                return

            self.text_label.config(text="ENFORCING...", fg="red")
            self.root.update()
            
            title = self.get_active_window_title().lower()
            browsers = ["firefox", "chrome", "edge", "brave", "browser"]
            
            is_browser = any(b in (exe_name or "").lower() for b in browsers) or \
                         any(b in title for b in browsers)

            if is_browser:
                # Targeted Tab Closing: Focus browser first, then send keys
                hwnd = win32gui.GetForegroundWindow()
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.1)
                pyautogui.hotkey('ctrl', 'w') 
                print(f"Sent Ctrl+W to browser: {exe_name}")
            else:
                # Kill standalone apps
                subprocess.run(["taskkill", "/F", "/IM", exe_name], capture_output=True, check=False)
                print(f"Taskkilled app: {exe_name}")
            
        except Exception as e:
            print(f"Enforcement error: {e}")

    def verify_reason(self, reason):
        check_prompt = f"User is on a distracting app. They said: '{reason}'. Is this a valid work-related reason? Reply ONLY 'YES' or 'NO'."
        try:
            response = ollama.chat(model='llama3', messages=[{'role': 'user', 'content': check_prompt}])
            return "YES" in response['message']['content'].upper()
        except: return False 

    def interrogate(self, target_exe):
        if self.is_interrogating: return
        
        self.is_interrogating = True
        self.status_label.config(text="❓", fg="yellow")
        
        self.dialog_win = tk.Toplevel(self.root)
        self.dialog_win.title("Mojo Interrogation")
        self.dialog_win.attributes("-topmost", True)
        self.dialog_win.geometry("300x180+600+400")
        
        tk.Label(self.dialog_win, text=f"WHY IS THIS OPEN?\n{target_exe}", font=("Arial", 10, "bold")).pack(pady=10)
        entry = tk.Entry(self.dialog_win)
        entry.pack(pady=5)
        entry.focus_set()

        def submit():
            reason = entry.get()
            if not reason or not self.verify_reason(reason):
                self.force_close_distractions(target_exe)
            else:
                self.grace_period_until = time.time() + 300
            self.close_dialog()

        tk.Button(self.dialog_win, text="Submit", command=submit).pack(pady=10)
        self.dialog_win.protocol("WM_DELETE_WINDOW", self.close_dialog)

    def close_dialog(self):
        if self.dialog_win:
            self.dialog_win.destroy()
            self.dialog_win = None
        self.is_interrogating = False

    def vision_loop(self):
        while True:
            if time.time() < self.grace_period_until:
                time.sleep(1)
                continue

            current_title = self.get_active_window_title()
            current_exe = self.get_active_app_info()

            # SYSTEM PROTECTION: Ignore Mojo and Windows Explorer
            mojo_identifiers = ["Mojo", "Mojo Interrogation", "tk"]
            is_mojo = any(id in current_title for id in mojo_identifiers)
            is_explorer = current_exe and current_exe.lower() == "explorer.exe"

            if is_mojo or is_explorer or (current_exe and "python" in current_exe.lower() and self.is_interrogating):
                time.sleep(0.5)
                continue

            self.take_optimized_screenshot()

            try:
                prompt = f"""
                Analyze the user's screen and Window Title.
                WINDOW TITLE: {current_title}
                
                Productivity Assessment Rules:
                1. 'PRODUCTIVE': Only if the window title or screen shows Coding (VS Code, Cursor, GitHub), Terminal/PowerShell, or Technical Documentation (StackOverflow, MDN, Documentation sites).
                2. 'DISTRACTED': If the title or screen shows Music (Spotify, Apple Music), Social Media, Videos (YouTube, Netflix), Shopping, or Character sites (VRoid, etc.).
                3. YouTube specifically: Only 'PRODUCTIVE' if the title explicitly includes 'Tutorial', 'Lesson', 'Coding', or 'Course'. Otherwise, 'DISTRACTED'.
                
                Analyze the Window Title '{current_title}' carefully.
                Reply ONLY 'PRODUCTIVE' or 'DISTRACTED'.
                """
                
                response = ollama.chat(
                    model='llava', 
                    messages=[{'role': 'user', 'content': prompt, 'images': ['screen_small.png']}],
                    options={'num_predict': 5, 'temperature': 0}
                )
                
                raw_output = response['message']['content'].strip().upper()
                print(f"Status: {raw_output} | App: {current_exe} | Title: {current_title}")

                if "PRODUCTIVE" in raw_output:
                    if self.is_interrogating:
                        self.root.after(0, self.close_dialog)
                    self.status_label.config(text="🔥", fg="lime")
                    self.text_label.config(text="LOCKED IN", fg="white")
                
                elif "DISTRACTED" in raw_output:
                    if not self.is_interrogating:
                        self.root.after(0, lambda: self.interrogate(current_exe))
                    self.status_label.config(text="🚨", fg="red")
                    self.text_label.config(text="DISTRACTED", fg="red")

            except Exception as e:
                print(f"Vision Error: {e}")

            time.sleep(0.5)

if __name__ == "__main__":
    MojoApp()