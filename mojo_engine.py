import tkinter as tk
import threading
import mss
import ollama
import time
from PIL import Image,ImageTk
import os
import subprocess
import pyautogui
import win32gui
import win32process
import psutil
import win32con
import time
 

class MojoApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Mojo") 
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        
        # Set a color to be completely transparent
        self.bg_color = '#000001' # Almost black, used as transparency key
        self.root.config(bg=self.bg_color)
        self.root.attributes("-transparentcolor", self.bg_color)
        
        self.root.geometry("250x250+1300+700") 

        # --- DRAGGABLE LOGIC ---
        self._offsetx = 0
        self._offsety = 0
        self.root.bind('<Button-1>', self.start_drag)
        self.root.bind('<B1-Motion>', self.on_drag)

        # --- GLOWING ORB UI ---
        # 1. Load the Glow Image (You need a glowing circle PNG with transparency)
        try:
            self.orb_image = Image.open("orb.png").resize((200, 200), Image.Resampling.LANCZOS)
            self.orb_photo = ImageTk.PhotoImage(self.orb_image)
            
            self.bg_label = tk.Label(self.root, image=self.orb_photo, bg=self.bg_color)
            self.bg_label.place(x=25, y=25) # Center the 200px orb in the 250px window
            
            # Re-bind drag to the background image so you can grab the orb itself
            self.bg_label.bind('<Button-1>', self.start_drag)
            self.bg_label.bind('<B1-Motion>', self.on_drag)
        except Exception as e:
            print(f"Image load error: {e}. Falling back to basic circle.")

        # 2. Status Icon (centered inside the orb)
        self.status_label = tk.Label(self.root, text="🔥", font=("Arial", 40), bg='#1a1a1a', fg="lime")
        # Note: 'bg' should match the center color of your orb image for a seamless look
        self.status_label.place(relx=0.5, rely=0.45, anchor='center')
        
        self.text_label = tk.Label(self.root, text="LOCKED IN", font=("Arial", 10, "bold"), bg='#1a1a1a', fg="white")
        self.text_label.place(relx=0.5, rely=0.65, anchor='center')

        # ... (Rest of your original logic: interrogation, vision_loop, etc.) ...
        self.is_interrogating = False
        self.grace_period_until = 0  
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
    
    def force_close_distractions(self, exe_name, target_hwnd=None): # Added target_hwnd
        try:
            protected_exes = ["python.exe", "explorer.exe", "taskmgr.exe"]
            if exe_name and exe_name.lower() in protected_exes:
                return

            # If no specific hwnd was passed, get the current one
            hwnd = target_hwnd if target_hwnd else win32gui.GetForegroundWindow()
            
            self.text_label.config(text="ENFORCING...", fg="red")
            self.root.update()
            
            title = win32gui.GetWindowText(hwnd).lower()
            browsers = ["firefox", "chrome", "edge", "brave", "browser"]
            is_browser = any(b in (exe_name or "").lower() for b in browsers) or \
                        any(b in title for b in browsers)

            if is_browser:
                # FORCE focus back to the browser so it can receive Ctrl+W
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.3) # Slightly longer delay to ensure focus
                
                pyautogui.hotkey('ctrl', 'w') 
                print(f"Sent Ctrl+W to browser: {exe_name}")
            else:
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
    
    # CAPTURE THE DISTRACTING WINDOW ID NOW
        distraction_hwnd = win32gui.GetForegroundWindow()
    
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
                # PASS THE CAPTURED HWND HERE
                self.force_close_distractions(target_exe, distraction_hwnd)
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