import os
import sys
import json
import tkinter as tk
from tkinter import messagebox
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

# --- PORTABLE PATHS ---
def _get_app_dir():
    """Directory for config and data; next to exe when frozen, else script dir."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _setup_tesseract_path():
    """Use tesseract in cwd if present, else fallback to Program Files."""
    cwd = os.getcwd()
    candidates = [
        os.path.join(cwd, "tesseract", "tesseract.exe"),
        os.path.join(cwd, "Tesseract-OCR", "tesseract.exe"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            pytesseract.pytesseract.tesseract_cmd = path
            return
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

_setup_tesseract_path()

# --- API KEY (config.json) ---
CONFIG_FILENAME = "config.json"

def _config_path():
    return os.path.join(_get_app_dir(), CONFIG_FILENAME)

def _load_api_key_from_config():
    try:
        path = _config_path()
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("GEMINI_API_KEY") or data.get("gemini_api_key")
    except Exception:
        pass
    return None

def _save_api_key_to_config(api_key: str):
    try:
        path = _config_path()
        data = {}
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
        data["GEMINI_API_KEY"] = api_key.strip()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def _ask_api_key_popup():
    """Show a simple Tkinter popup to enter Gemini API Key. Returns key or None."""
    root = tk.Tk()
    root.title("Mojo — API Key")
    root.resizable(False, False)
    root.geometry("400x120")
    root.eval("tk::PlaceWindow . center")
    var = tk.StringVar()
    tk.Label(root, text="Enter your Gemini API Key:", font=("Segoe UI", 10)).pack(pady=(12, 4))
    entry = tk.Entry(root, textvariable=var, width=50, show="*")
    entry.pack(pady=4, padx=12)
    result = [None]

    def ok():
        result[0] = (var.get() or "").strip() or None
        root.destroy()

    def cancel():
        root.destroy()

    tk.Frame(root).pack(pady=4)
    tk.Button(root, text="OK", command=ok, width=10).pack(side=tk.LEFT, padx=4)
    tk.Button(root, text="Cancel", command=cancel, width=10).pack(side=tk.LEFT)
    entry.focus()
    root.mainloop()
    return result[0]

# --- CONFIGURATION ---
USER_GOAL = "General Productivity, Research, School work, College Work, LLM Usage, AI Usage, Python Coding, and AI Research, General Productivity, Note Taking, Time Management "

WHITELISTED_EXES = ["powershell.exe", "pwsh.exe", "cmd.exe", "code.exe", "cursor.exe", "python.exe", "pycharm64.exe", "searchhost.exe", "searchui.exe", "searchapp.exe", "whatsapp.exe", "obs64.exe", "windowsterminal.exe"]
WHITELISTED_TITLES = ["gemini", "chatgpt", "github", "stackoverflow", "documentation", "localhost", "searchhost", "search ui", "search app", "visual studio code", "terminal", "powershell"]

# Descriptors for common distraction/chat/game applications
DISTRACTED_EXES = [
    "discord.exe", "steam.exe", "epicgameslauncher.exe", "robloxplayerlauncher.exe",
    "spotify.exe", "twitch.exe", "leagueclient.exe", "valorant.exe", "battlenet.exe",
]
DISTRACTED_TITLES = [
    "discord", "steam", "epic games", "roblox", "twitch", "spotify", "league of legends",
    "valorant", "battle.net", "call of duty", "fortnite", "minecraft", "vscode dev", "youtube",
]

class MojoApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Mojo")
        # Normal window so it appears in taskbar and can be closed with X
        self.root.overrideredirect(False)
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

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

        # Resolve Gemini API key: env -> config.json -> popup
        api_key = os.environ.get("GEMINI_API_KEY") or _load_api_key_from_config()
        if not (api_key and api_key.strip()):
            api_key = _ask_api_key_popup()
            if api_key:
                _save_api_key_to_config(api_key)
        if api_key:
            os.environ["GEMINI_API_KEY"] = api_key.strip()

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

    def _on_close(self):
        """Handle taskbar/window close (X button) — quit the app."""
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
        os._exit(0)

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
        """Capture the active window and OCR it, focusing on key areas like titles.

        For browsers, prioritize OCR of the top area (URL bar, tab title, video/article title).
        """
        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd and win32gui.IsWindow(hwnd):
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                if right > left and bottom > top:
                    with mss.mss() as sct:
                        monitor = {"left": left, "top": top, "width": right - left, "height": bottom - top}
                        sct_img = sct.grab(monitor)
                        img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                        img.save("vision_input.png")

                        # OCR the full window
                        try:
                            full_ocr = pytesseract.image_to_string(img).strip()
                        except Exception:
                            full_ocr = ""

                        # For browsers, OCR the top 20% more carefully (likely contains title/URL)
                        height = img.height
                        top_crop = img.crop((0, 0, img.width, int(height * 0.2)))
                        try:
                            title_ocr = pytesseract.image_to_string(top_crop).strip()
                        except Exception:
                            title_ocr = ""

                        # Combine: prioritize title area, then full
                        combined_ocr = f"{title_ocr}\n{full_ocr}".strip()
                        return combined_ocr
        except Exception:
            pass

        # Fallback: full screen capture
        with mss.mss() as sct:
            sct.shot(output="temp_screen.png")
            img = Image.open("temp_screen.png")
            img.save("vision_input.png")
            try:
                ocr_text = pytesseract.image_to_string(img).strip()
            except Exception:
                ocr_text = ""
            return ocr_text

    def _fallback_productive_check(self, window_title: str, tab_text: str) -> bool:
        """When API is unavailable, use simple keyword heuristics. Returns True if productive."""
        combined = f"{window_title} {tab_text}".lower()

        # Treat core system utilities as productive/neutral (not distractions)
        if any(x in combined for x in ["search host", "searchhost", "search ui", "searchapp"]):
            return True

        distracted_keywords = [
            "youtube.com", "youtube ", "netflix", "prime video", "twitch.tv",
            "twitter.com", "x.com", "instagram", "tiktok", "facebook.com", "reddit.com",
            "amazon.com", "flipkart", "ebay", "shopping", "game", "movie", "series",
            "nsfw content", "discord", "steam", "epic games", "roblox", "spotify",
            "twitch", "league of legends", "valorant", "battle.net", "minecraft",
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
        return False  # when in doubt, treat as distracted to encourage better focus

    def vision_loop(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        try:
            client = genai.Client(api_key=api_key)
        except Exception as e:
            err_msg = str(e).lower()
            if "api_key" in err_msg or "invalid" in err_msg or "401" in err_msg or "403" in err_msg:
                def show_invalid_key():
                    messagebox.showerror(
                        "Invalid API Key",
                        "The Gemini API key appears to be invalid or was rejected.\n\n"
                        "Edit or delete config.json next to the app and restart to enter a new key."
                    )
                self.root.after(0, show_invalid_key)
            else:
                self.root.after(0, lambda: messagebox.showerror("Gemini Error", f"Failed to initialize Gemini client: {e}"))
            return
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
            screen_ocr = self.get_screen_data()  # Saves 'vision_input.png'

            low_title = current_title.lower()
            exe_low = current_exe.lower() if current_exe else ""
            ocr_text = (screen_ocr or "").lower()

            # Check Whitelists
            if exe_low in WHITELISTED_EXES or any(wt in low_title for wt in WHITELISTED_TITLES):
                self.update_ui("🔥", "LOCKED IN", "lime", "white")
                time.sleep(3)
                continue

            # Check Ignored
            ignored = ["mojo", "tk", "explorer.exe", "task manager", "settings", "search host", "search ui", "search app"]
            if any(x in low_title for x in ignored) or exe_low in ignored:
                time.sleep(1)
                continue

            # Quick heuristic: known chat/game apps are treated as distractions unless whitelisted
            if exe_low in DISTRACTED_EXES or any(dt in low_title for dt in DISTRACTED_TITLES) or any(dt in ocr_text for dt in DISTRACTED_TITLES):
                print("DECISION: DISTRACTED (known app keywords)")
                if "mojo" not in (current_exe or "").lower():
                    self.update_ui("🚫", "DISTRACTED", "red", "red")
                    self.interrogate(current_exe, current_hwnd, ocr_text)
                time.sleep(3)
                continue

            # Print everything we're seeing
            print("\n" + "=" * 50)
            print("--- WHAT I'M SEEING ---")
            print(f"  Active window title: {current_title!r}")
            print(f"  Process (exe):       {current_exe!r}")
            print(f"  OCR window text:     {ocr_text[:300]!r}")
            print("  (Screenshot saved:   vision_input.png)")
            print("=" * 50)

            # If we're in quota cooldown (429), skip API and use keyword fallback
            if time.time() < self.quota_cooldown_until:
                rem = int(self.quota_cooldown_until - time.time())
                print(f"API in cooldown ({rem}s left) — using keyword fallback")
                is_productive = self._fallback_productive_check(current_title, ocr_text)
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
                "SYSTEM: You are a strict productivity monitor. You MUST base your decision on what you SEE in the attached screenshot.\n\n"
                "PRIMARY: Look at the IMAGE. The image shows the top of the user's screen (browser URL bar, tab bar, and visible page content).\n"
                "Your job is to classify whether what is VISUALLY on screen (URL, search query, page content, visible text/links) is productive work or a distraction.\n\n"
                f"USER GOAL: {USER_GOAL}\n\n"
                "Use this context only to support what you see in the image:\n"
                f"Window title: {current_title}\n"
                f"OCR of window content (may be noisy): {ocr_text[:220]}\n\n"
                "PRODUCTIVE = what's on screen is clearly work: code, docs, GitHub, StackOverflow, IDE, terminal, AI tools for work, research, study.\n\n"
                "DISTRACTED = what's on screen is clearly not work. ALWAYS mark DISTRACTED if you see ANY of the following in the image:\n"
                "- Inappropriate or adult content, NSFW, or search queries/results that are sexual, pornographic, or not work-related\n"
                "- Entertainment: YouTube/Netflix/Twitch for videos, social media feeds (Twitter, Instagram, TikTok, Facebook, Reddit for casual browsing)\n"
                "- Chat/messaging or gaming apps and platforms (Discord, Steam, Epic Games, Roblox, Valorant, League, etc.)\n"
                "- Shopping (Amazon, etc.) unless clearly work-related\n"
                "- Memes, gossip, celebrity news, random time-wasting sites\n"
                "- Google (or any search) showing results for inappropriate queries, jokes, or off-topic searches — the SEARCH RESULTS and visible page content decide, not the fact that it's a search\n\n"
                "CRITICAL: If the visible URL bar, search box, or page content shows an inappropriate search term, inappropriate site, or clearly non-work content, you MUST output STATUS: DISTRACTED.\n"
                "When in doubt between productive vs distracted, prefer DISTRACTED for anything that looks like entertainment, adult content, or off-topic browsing.\n\n"
                "OUTPUT exactly: 'REASON: <very short reason> | STATUS: <PRODUCTIVE or DISTRACTED>'"
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
                            self.interrogate(current_exe, current_hwnd, ocr_text)
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
                    is_productive = self._fallback_productive_check(current_title, ocr_text)
                    if is_productive:
                        print("DECISION: PRODUCTIVE (fallback)")
                        self.update_ui("🔥", "LOCKED IN", "lime", "white")
                    else:
                        print("DECISION: DISTRACTED (fallback)")
                        if "mojo" not in (current_exe or "").lower():
                            self.update_ui("🚫", "DISTRACTED", "red", "red")
                            self.interrogate(current_exe, current_hwnd, ocr_text)
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

    def interrogate(self, target_exe, target_hwnd, ocr_text=""):
        if self.is_interrogating: return
        self.is_interrogating = True
        self.root.after(100, lambda: self._show_interrogate_dialog(target_exe, target_hwnd, ocr_text))

    def _show_interrogate_dialog(self, target_exe, target_hwnd, ocr_text=""):
        def cleanup():
            # Close MojoUI chat window, if any
            if hasattr(self.ui, 'close_interrogation_dialog'):
                try: self.ui.close_interrogation_dialog()
                except: pass
            
            # 3. Reset Flag
            self.is_interrogating = False
            self.update_ui("🔥", "LOCKED IN", "lime", "white")
            print("CLEANUP: All interrogation windows closed.")

        def give_grace(duration_min: int = 1):
            duration_min = max(1, min(duration_min, 20))
            print(f"AGENT DECISION: GRANT ACCESS ({duration_min} minute(s))")
            self.grace_period_until = time.time() + (duration_min * 60)
            cleanup()

        try:
            self.ui.show_interrogation_dialog(
                target_exe, target_hwnd, ocr_text,
                # LLM inside MojoUI decides: GRANT_ACCESS vs DENY_ACCESS and how long.
                on_valid_reason=lambda duration: give_grace(duration if isinstance(duration, int) else 1),
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