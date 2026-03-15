import os
import tkinter as tk
from dotenv import load_dotenv

load_dotenv()  # load .env into os.environ
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
import google.genai as genai
from google.genai import types

from mojo_ui import MojoUI 

# --- CONFIGURATION ---
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
USER_GOAL = "General Productivity, Research, School work, College Work, LLM Usage, AI Usage, Python Coding, and AI Research, General Productivity, Note Taking, Time Management "

WHITELISTED_EXES = ["powershell.exe", "pwsh.exe", "cmd.exe", "code.exe", "cursor.exe", "python.exe", "pycharm64.exe", "SearchHost.exe", "WhatsApp.exe", "obs64.exe", "WindowsTerminal.exe"]
WHITELISTED_TITLES = ["gemini", "chatgpt", "github", "stackoverflow", "documentation", "localhost", "SearchHost", "visual studio code", "terminal", "powershell"]

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
        self.quota_cooldown_until = 0  # skip API calls until this time (429 backoff)
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

    def _fallback_productive_check(self, window_title: str, tab_text: str) -> bool:
        """When API is unavailable, use simple keyword heuristics. Returns True if productive."""
        combined = f"{window_title} {tab_text}".lower()
        distracted_keywords = [
            "youtube.com", "youtube ", "netflix", "prime video", "twitch.tv",
            "twitter.com", "x.com", "instagram", "tiktok", "facebook.com", "reddit.com",
            "amazon.com", "flipkart", "ebay", "shopping", "game", "movie", "series",
        ]
        productive_keywords = [
            "github", "stackoverflow", "docs.", "documentation", "google cloud",
            "console", "developer", "code", "cursor", "vs code", "pycharm",
            "chatgpt", "gemini", "claude", "ai.google", "localhost", "terminal",
        ]
        if any(k in combined for k in distracted_keywords):
            return False
        if any(k in combined for k in productive_keywords):
            return True
        return True  # when in doubt, treat as productive

    def vision_loop(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        client = genai.Client(api_key=api_key)
        # Use current model IDs (gemini-1.5-flash is deprecated on v1beta); try in order
        GEMINI_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash-latest", "gemini-1.5-flash-001"]
        model_index = 0

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
            tab_titles = self.get_screen_data() # This saves 'vision_input.png'

            low_title = current_title.lower()
            exe_low = current_exe.lower() if current_exe else ""

            # Check Whitelists
            if exe_low in WHITELISTED_EXES or any(wt in low_title for wt in WHITELISTED_TITLES):
                self.update_ui("🔥", "LOCKED IN", "lime", "white")
                time.sleep(3)
                continue

            # Check Ignored
            ignored = ["mojo", "tk", "explorer.exe", "task manager", "settings", "search host"]
            if any(x in low_title for x in ignored) or exe_low in ignored:
                time.sleep(1)
                continue

            # Print everything we're seeing
            print("\n" + "=" * 50)
            print("--- WHAT I'M SEEING ---")
            print(f"  Active window title: {current_title!r}")
            print(f"  Process (exe):       {current_exe!r}")
            print(f"  OCR tab/top text:    {tab_titles[:300]!r}")
            print("  (Screenshot saved:   vision_input.png)")
            print("=" * 50)

            # If we're in quota cooldown (429), skip API and use keyword fallback
            if time.time() < self.quota_cooldown_until:
                rem = int(self.quota_cooldown_until - time.time())
                print(f"API in cooldown ({rem}s left) — using keyword fallback")
                is_productive = self._fallback_productive_check(current_title, tab_titles)
                if is_productive:
                    print("DECISION: PRODUCTIVE (fallback)")
                    self.update_ui("🔥", "LOCKED IN", "lime", "white")
                else:
                    print("DECISION: DISTRACTED (fallback)")
                    if "mojo" not in (current_exe or "").lower():
                        self.update_ui("🚫", "DISTRACTED", "red", "red")
                        self.interrogate(current_exe, current_hwnd)
                time.sleep(5)
                continue

            print("EVALUATING WITH AI...")
            prompt = (
                "SYSTEM: You are a strict productivity monitor.\n"
                "You ONLY judge the SINGLE ACTIVE BROWSER TAB currently visible.\n\n"
                f"USER GOAL: {USER_GOAL}\n"
                f"ACTIVE WINDOW TITLE: {current_title}\n"
                f"ACTIVE TAB/TOP-BAR TEXT (OCR): {tab_titles[:220]}\n\n"
                "IMPORTANT:\n"
                "Educational tutorials, lectures, or programming lessons are PRODUCTIVE even if they are on YouTube.\n\n"
                "PRODUCTIVE EXAMPLES:\n"
                "- Programming tutorials\n"
                "- Machine learning lectures\n"
                "- Technical conference talks\n"
                "- Coding walkthroughs\n"
                "- AI research explanations\n"
                "- GitHub, documentation, StackOverflow\n"
                "- AI tools like ChatGPT, Gemini, Claude\n\n"
                "DISTRACTED EXAMPLES:\n"
                "- Music videos\n"
                "- Entertainment videos\n"
                "- Movie clips\n"
                "- Gaming videos\n"
                "- Social media browsing\n"
                "- Shopping websites\n\n"
                "If the video is educational and related to coding, AI, or research → PRODUCTIVE.\n"
                "If the video is entertainment or music → DISTRACTED.\n\n"
                "OUTPUT:\n"
                "REASON: <very short reason> | STATUS: <PRODUCTIVE/DISTRACTED>"
            )
            try:
                raw_img = Image.open("vision_input.png")
                model_id = GEMINI_MODELS[model_index]
                response = client.models.generate_content(
                    model=model_id,
                    contents=[prompt, raw_img]
                )

                if response.text:
                    result = response.text.upper()
                    print(f"AI raw response: {response.text.strip()}")

                    if "STATUS: PRODUCTIVE" not in result:
                        print("DECISION: DISTRACTED")
                        if "mojo" not in (current_exe or "").lower():
                            self.update_ui("🚫", "DISTRACTED", "red", "red")
                            self.interrogate(current_exe, current_hwnd)
                    else:
                        print("DECISION: PRODUCTIVE")
                        self.update_ui("🔥", "LOCKED IN", "lime", "white")
                else:
                    print("DECISION: (none — empty response / Safety Filter?)")
                    self.update_ui("🔍", "CHECKING", "gray", "white")

            except Exception as e:
                err_str = str(e).upper()
                if "404" in err_str or "NOT_FOUND" in err_str:
                    model_index = min(model_index + 1, len(GEMINI_MODELS) - 1)
                    print(f"Gemini model not found, trying {GEMINI_MODELS[model_index]}...")
                elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    self.quota_cooldown_until = time.time() + 60
                    print("Gemini quota exceeded. Waiting 60s before retrying API.")
                    print("Using keyword fallback for this check and the next 60s.")
                    is_productive = self._fallback_productive_check(current_title, tab_titles)
                    if is_productive:
                        print("DECISION: PRODUCTIVE (fallback)")
                        self.update_ui("🔥", "LOCKED IN", "lime", "white")
                    else:
                        print("DECISION: DISTRACTED (fallback)")
                        if "mojo" not in (current_exe or "").lower():
                            self.update_ui("🚫", "DISTRACTED", "red", "red")
                            self.interrogate(current_exe, current_hwnd)
                else:
                    print(f"Gemini API Error: {e}")
                    print("DECISION: (skipped — API error)")
                    self.update_ui("🔍", "CHECKING", "gray", "white")

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
        def cleanup():
            # Close MojoUI chat window, if any
            if hasattr(self.ui, 'close_interrogation_dialog'):
                try: self.ui.close_interrogation_dialog()
                except: pass
            
            # 3. Reset Flag
            self.is_interrogating = False
            self.update_ui("🔥", "LOCKED IN", "lime", "white")
            print("CLEANUP: All interrogation windows closed.")

        def give_grace():
            print("AGENT DECISION: GRANT ACCESS (1 minute)")
            self.grace_period_until = time.time() + 60
            cleanup()

        try:
            self.ui.show_interrogation_dialog(
                target_exe, target_hwnd,
                # LLM inside MojoUI decides: GRANT_ACCESS vs DENY_ACCESS.
                on_valid_reason=lambda r: give_grace(),
                on_invalid=lambda exe, hwnd: (
                    print(f"AGENT DECISION: DENY ACCESS, closing {exe or target_exe}"),
                    self.force_close_distractions(exe or target_exe, hwnd or target_hwnd),
                    cleanup()
                ),
                on_close=cleanup
            )
        except Exception as e:
            print(f"UI Launch Error: {e}")
            cleanup()

if __name__ == "__main__":
    MojoApp()