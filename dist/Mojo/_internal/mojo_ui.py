"""
mojo_ui.py — All visual UI for Mojo.
Drop this file next to mojo_engine.py.

Public API:
    ui = MojoUI(root, bg_color)
    ui.update_state(text)
    ui.reposition_bubbles()
    ui.show_interrogation_dialog(target_exe, target_hwnd,
                                 on_valid_reason, on_invalid, on_close)
"""

import re
import tkinter as tk
import tkinter.font as tkfont
import math
import time
import threading
import google.genai as genai
import os


# ── Personality messages ───────────────────────────────────────────────────────
MESSAGES = {
    "LOCKED IN": [
        "You're locked in. Let's go 🔥",
        "Deep focus. Don't stop now 💪",
        "You're on a roll. Keep it up!",
        "Crushing it today 🚀",
    ],
    "DISTRACTED": [
        "What are you doing here? Get back to work! 😤",
        "Tab's closed! Time to channel all that focus 🚀",
        "You've been neglected. Let's get you back on track! 💪",
        "Really? Close it. You know better 🚫",
        "I see you slacking. Back to work now 👁️",
        "That's not on your goal list. Close it! ✂️",
    ],
    "GRACE PERIOD": [
        "Alright, 5 min break. Make it count ⏳",
        "Grace period started. Clock's ticking ⏱️",
        "Fine. 5 minutes. Then back to work.",
    ],
    "THINKING": [
        "Checking what you're up to... 🔍",
        "Hold on, scanning your screen 🤔",
        "Analysing... one sec",
    ],
}

STATE_COLORS = {
    "LOCKED IN":    (34,  197,  94),
    "DISTRACTED":   (239,  68,  68),
    "GRACE PERIOD": (  6, 182, 212),
    "THINKING":     (168,  85, 247),
}

ACCENT_HEX = {
    "LOCKED IN":    "#22c55e",
    "DISTRACTED":   "#ef4444",
    "GRACE PERIOD": "#06b6d4",
    "THINKING":     "#a855f7",
}

STATE_PULSE = {
    "LOCKED IN":    {"pulse": 0.05, "speed": 0.025},
    "DISTRACTED":   {"pulse": 0.22, "speed": 0.11},
    "GRACE PERIOD": {"pulse": 0.07, "speed": 0.040},
    "THINKING":     {"pulse": 0.04, "speed": 0.055},
}

BUBBLE_RIGHT_MARGIN = 24
BUBBLE_TOP_START    = 80
BUBBLE_GAP          = 12

# ── Mojo's chat personality system prompt ─────────────────────────────────────
CHAT_SYSTEM = """You are Mojo — a chill but honest productivity buddy. The user just got caught on something distracting.

Your job: have a short, natural, human-like conversation to figure out if they deserve a break or not. 
Talk like a real friend. Keep it brief (1 or 2 short sentences). No robotic structures or bullet points.

⚠️ HARD RULES FOR THE SYSTEM (User won't see these tags):
- Your response MUST END with exactly ONE of these tags: [CLOSE_NOW], [GRANT_ACCESS n], or [DENY_ACCESS].
- [GRANT_ACCESS n] = You are giving them a break. 'n' is the number of minutes (e.g., [GRANT_ACCESS 5]). Only use this if they gave a valid reason AND you two agreed on a duration.
- [DENY_ACCESS] = You are keeping the conversation going but you haven't given them a pass yet. Use this when asking "Why?" or "How long?"
- [CLOSE_NOW] = You are shutting down the distraction right now because their excuse was bad or they admitted fault.

VALID reasons (earn a break): genuinely tired after working hard, bathroom, getting water/food, urgent message, earned rest.
INVALID (close immediately): "just listening to music", "just chilling", "bored", vague answers, endless scrolling.

Flow:
1. They say "sorry" or admit fault → Say "No worries, back to the grind." ending with [CLOSE_NOW].
2. They haven't given a reason → Ask "What's up?" ending with [DENY_ACCESS].
3. They give a VALID reason but no time limit → Say "Fair enough, how many minutes do you need?" ending with [DENY_ACCESS].
4. They give a valid reason AND a time limit (or answer your question) → Say "Alright, take 5." ending with [GRANT_ACCESS 5] (replace 5 with their number).
5. They give an INVALID reason → Call them out gently and close it. "Nah, nice try. Close it." ending with [CLOSE_NOW].

Be brief and conversational!
"""


class MojoUI:
    ORB_SIZE   = 80
    ORB_RADIUS = 22

    def __init__(self, root: tk.Tk, bg_color: str = "#000001", app=None):
        self.root     = root
        self.bg_color = bg_color
        self.app      = app  # Reference to MojoApp for accessing grace_period_until
        self.timer_window     = None   # Separate popup window for grace period timer
        self._timer_total     = 0.0    # Total duration of current grace period
        self._timer_detached  = False  # True once user drags the timer away from orb

        self.root.geometry(f"{self.ORB_SIZE}x{self.ORB_SIZE}+1400+750")

        self.canvas = tk.Canvas(
            self.root,
            width=self.ORB_SIZE,
            height=self.ORB_SIZE,
            bg=self.bg_color,
            highlightthickness=0,
        )
        self.canvas.pack()

        self._state       = "LOCKED IN"
        self._t           = 0
        self._ring_phases = [0.0, 0.38, 0.72]
        self._bubble_wins = []
        self._last_state  = None

        self._tick()

    # ── Public API ─────────────────────────────────────────────────────────────

    def update_state(self, state: str):
        clean = state.strip().upper()
        if clean not in STATE_COLORS:
            clean = "THINKING"
        changed     = clean != self._last_state
        self._state = clean
        if changed:
            self._last_state = clean
            msgs = MESSAGES.get(clean, [])
            if msgs:
                self.root.after(0, lambda m=random.choice(msgs): self._push_bubble(m))

    def reposition_bubbles(self):
        self._restack_bubbles()

    def show_interrogation_dialog(
        self,
        target_exe,
        target_hwnd,
        ocr_text="",
        on_valid_reason=None,
        on_invalid=None,
        on_close=None,
    ):
        """Multi-turn chat dialog. Mojo negotiates with the user via llama3."""

        accent       = ACCENT_HEX.get(self._state, "#ef4444")
        chat_history = []   # list of {"role": "user"/"assistant", "content": str}

        # ── Window ────────────────────────────────────────────────────────────
        win = tk.Toplevel(self.root)
        win.title("Mojo")
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.9)
        win.configure(bg="#1c1c1e")

        # Canvas for rounded background
        canvas = tk.Canvas(win, bg="#1c1c1e", highlightthickness=0, width=550, height=700)
        canvas.pack(fill="both", expand=True)

        def draw_rounded_rect(canvas, x1, y1, x2, y2, r, fill, outline=""):
            canvas.create_arc(x1, y1, x1+2*r, y1+2*r, start=90, extent=90, fill=fill, outline=outline)
            canvas.create_arc(x2-2*r, y1, x2, y1+2*r, start=0, extent=90, fill=fill, outline=outline)
            canvas.create_arc(x1, y2-2*r, x1+2*r, y2, start=180, extent=90, fill=fill, outline=outline)
            canvas.create_arc(x2-2*r, y2-2*r, x2, y2, start=270, extent=90, fill=fill, outline=outline)
            canvas.create_rectangle(x1+r, y1, x2-r, y2, fill=fill, outline=outline)
            canvas.create_rectangle(x1, y1+r, x2, y2-r, fill=fill, outline=outline)

        draw_rounded_rect(canvas, 0, 0, 550, 700, 25, "#1c1c1e")

        # Coloured top bar
        top_bar = tk.Frame(win, bg=accent, height=4)
        canvas.create_window(275, 2, window=top_bar)
        top_bar.pack_propagate(False)
        top_bar.configure(width=550)

        # ── Header ────────────────────────────────────────────────────────────
        header_frame = tk.Frame(win, bg="#1c1c1e", padx=14, pady=10)
        canvas.create_window(275, 50, window=header_frame)

        avatar = tk.Frame(header_frame, bg="#1c1c1e", width=34, height=34)
        avatar.pack(side="left", padx=(0, 10))
        avatar.pack_propagate(False)
        tk.Label(avatar, text="🤖", font=("Segoe UI", 16),
                 bg="#1c1c1e").place(relx=0.5, rely=0.5, anchor="center")

        title_col = tk.Frame(header_frame, bg="#1c1c1e")
        title_col.pack(side="left")
        tk.Label(title_col, text="Mojo",
                 font=("Segoe UI", 12, "bold"), fg="#f4f4f5",
                 bg="#1c1c1e").pack(anchor="w")
        tk.Label(title_col, text=f"Caught: {target_exe or 'unknown'}",
                 font=("Segoe UI", 9), fg="#52525b",
                 bg="#1c1c1e").pack(anchor="w")

        # Separator
        sep_frame = tk.Frame(win, bg="#2a2a2e", height=1)
        canvas.create_window(275, 90, window=sep_frame)
        sep_frame.pack_propagate(False)
        sep_frame.configure(width=500)

        # ── Chat area (scrollable) ─────────────────────────────────────────────
        # Chat frame on canvas
        chat_container = tk.Frame(win, bg="#1c1c1e")
        canvas.create_window(275, 310, window=chat_container)

        scrollbar = tk.Scrollbar(chat_container, bg="#1c1c1e", troughcolor="#1c1c1e",
                                 highlightthickness=0, bd=0)
        scrollbar.pack(side="right", fill="y")

        chat_canvas = tk.Canvas(chat_container, bg="#1c1c1e", width=480, height=350,
                                highlightthickness=0, yscrollcommand=scrollbar.set)
        chat_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=chat_canvas.yview)

        msg_frame = tk.Frame(chat_canvas, bg="#1c1c1e")
        chat_canvas.create_window((0, 0), window=msg_frame, anchor="nw", width=480)

        def _on_frame_configure(e):
            chat_canvas.configure(scrollregion=chat_canvas.bbox("all"))
            chat_canvas.yview_moveto(1.0)

        msg_frame.bind("<Configure>", _on_frame_configure)

        # ── Typing indicator ──────────────────────────────────────────────────
        typing_var = tk.StringVar(value="")
        typing_frame = tk.Frame(win, bg="#1c1c1e", padx=14)
        canvas.create_window(275, 555, window=typing_frame)
        typing_lbl = tk.Label(typing_frame, textvariable=typing_var,
                              font=("Segoe UI", 9), fg="#52525b",
                              bg="#1c1c1e", anchor="w")
        typing_lbl.pack(fill="x")

        # ── Input row ─────────────────────────────────────────────────────────
        # Input separator
        input_sep_frame = tk.Frame(win, bg="#2a2a2e", height=1)
        canvas.create_window(275, 575, window=input_sep_frame)
        input_sep_frame.pack_propagate(False)
        input_sep_frame.configure(width=500)

        input_frame = tk.Frame(win, bg="#1c1c1e", padx=12, pady=10)
        canvas.create_window(275, 625, window=input_frame)

        entry_wrap = tk.Frame(input_frame, bg="#27272a",
                              highlightthickness=1,
                              highlightbackground="#3f3f46",
                              highlightcolor=accent,
                              relief="ridge", bd=2)
        entry_wrap.pack(side="left", fill="x", expand=True, padx=(0, 8))

        entry = tk.Entry(entry_wrap, font=("Segoe UI", 11),
                         bg="#27272a", fg="#f4f4f5",
                         insertbackground="#f4f4f5",
                         relief="flat", bd=7)
        entry.pack(fill="x")
        entry.focus_set()

        send_btn = tk.Button(input_frame, text="↑",
                             font=("Segoe UI", 12, "bold"),
                             bg=accent, fg="#ffffff",
                             activebackground=accent,
                             relief="flat", bd=0,
                             width=3, cursor="hand2")
        send_btn.pack(side="left")

        # ── Message renderer ──────────────────────────────────────────────────
        def _add_message(role: str, text: str):
            """Add a chat bubble. role = 'mojo' or 'user'."""
            is_mojo = role == "mojo"

            row = tk.Frame(msg_frame, bg="#1c1c1e", pady=3, padx=10)
            row.pack(fill="x")

            bubble_frame = tk.Frame(
                row,
                bg="#27272a" if is_mojo else accent,
                relief="ridge", bd=1
            )
            bubble = tk.Label(
                bubble_frame,
                text=text,
                wraplength=220,
                font=("Segoe UI", 11),
                fg="#f4f4f5" if is_mojo else "#ffffff",
                bg="#27272a" if is_mojo else accent,
                justify="left",
                padx=12, pady=8,
            )
            bubble.pack()

            if is_mojo:
                bubble_frame.pack(anchor="w")
            else:
                bubble_frame.pack(anchor="e")

        # ── LLM reply logic ───────────────────────────────────────────────────
        decision = {"result": None}   # "grant", "deny", or "close"
        user_turns = {"count": 0}
        MAX_USER_TURNS  = 5   # Auto-deny after this many turns with no resolution
        MIN_TURNS_TO_DENY = 3 # [DENY_ACCESS] won't close the app until this many turns

        def _llm_reply(user_msg: str):
            typing_var.set("Mojo is typing...")
            send_btn.config(state="disabled")
            entry.config(state="disabled")

            def _run():
                chat_history.append({"role": "user", "parts": [{"text": user_msg}]})

                try:
                    # Setup Gemini Client
                    api_key = os.environ.get("GEMINI_API_KEY")
                    client = genai.Client(api_key=api_key)
                    
                    # Convert chat history to Gemini format, omitting the system prompt
                    # we will pass the system prompt as system_instruction
                    gemini_history = []
                    for msg in chat_history:
                        role = "model" if msg["role"] == "assistant" else "user"
                        gemini_history.append({"role": role, "parts": msg["parts"]})

                    response = client.models.generate_content(
                        model='gemini-2.0-flash',
                        contents=gemini_history,
                        config=genai.types.GenerateContentConfig(
                            system_instruction=CHAT_SYSTEM,
                            temperature=0.7,
                        )
                    )
                    
                    if not response.text:
                        raise Exception("Empty response from AI")
                        
                    raw = response.text

                    def _parse_duration_minutes(text: str) -> int:
                        # Find a number (minutes) in the response. Allow any duration requested by user.
                        m = re.search(r"(\d+)\s*(min|mins|minutes)?", text, re.IGNORECASE)
                        if m:
                            try:
                                val = int(m.group(1))
                                return max(1, val)  # Allow any duration >= 1 minute
                            except Exception:
                                pass
                        return 1

                    duration_mins = _parse_duration_minutes(raw)
                    # Hide internal tags from the user view
                    visible = re.sub(r"\[GRANT_ACCESS.*?\]", "", raw, flags=re.IGNORECASE)
                    visible = re.sub(r"\[DENY_ACCESS\]", "", visible, flags=re.IGNORECASE)
                    visible = re.sub(r"\[CLOSE_NOW\]", "", visible, flags=re.IGNORECASE)
                    visible = visible.strip()
                    # If nothing left after removing tags, use a default message
                    if not visible:
                        visible = "Got it."

                    chat_history.append({"role": "assistant", "parts": [{"text": raw}]})

                    def safe_add_message():
                        try:
                            if win.winfo_exists():
                                _add_message("mojo", visible)
                        except Exception:
                            pass

                    def safe_clear_typing():
                        try:
                            if win.winfo_exists():
                                typing_var.set("")
                        except Exception:
                            pass

                    def safe_enable_send():
                        try:
                            if win.winfo_exists():
                                send_btn.config(state="normal")
                        except Exception:
                            pass

                    def safe_enable_entry():
                        try:
                            if win.winfo_exists():
                                entry.config(state="normal")
                        except Exception:
                            pass

                    def safe_focus_entry():
                        try:
                            if win.winfo_exists():
                                entry.focus_set()
                        except Exception:
                            pass

                    win.after(0, safe_add_message)
                    win.after(0, safe_clear_typing)
                    win.after(0, safe_enable_send)
                    win.after(0, safe_enable_entry)
                    win.after(0, safe_focus_entry)

                    # Check for explicit decision tags
                    raw_up = raw.upper()
                    if "[CLOSE_NOW]" in raw_up:
                        # Immediate close — user asked for it
                        decision["result"] = "close"
                        win.after(500, lambda: _resolve(-1))
                    elif "[GRANT_ACCESS" in raw_up:
                        # Break granted — act immediately
                        decision["result"] = "grant"
                        win.after(800, lambda: _resolve(duration_mins))
                    elif "[DENY_ACCESS]" in raw_up:
                        if user_turns["count"] >= MIN_TURNS_TO_DENY:
                            # Enough conversation — close now
                            print(f"[LLM] DENY after {user_turns['count']} turns — closing")
                            decision["result"] = "deny"
                            win.after(800, lambda: _resolve(-1))
                        else:
                            # Still early in conversation — keep talking, don't close yet
                            print(f"[LLM] DENY seen at turn {user_turns['count']} — holding off (need {MIN_TURNS_TO_DENY})")
                    else:
                        # LLM forgot to include a tag — check turn limit
                        print(f"[LLM] No action tag. Turn {user_turns['count']}/{MAX_USER_TURNS}")
                        if user_turns["count"] >= MAX_USER_TURNS:
                            print("[LLM] Max turns reached — auto-denying")
                            decision["result"] = "deny"
                            def _auto_deny_msg():
                                try:
                                    if win.winfo_exists():
                                        _add_message("mojo", "Alright, closing it. Back to work!")
                                except Exception:
                                    pass
                            win.after(0, _auto_deny_msg)
                            win.after(1200, lambda: _resolve(-1))

                except Exception as e:
                    print(f"Chat LLM error: {e}")
                    # On LLM error, auto-deny so the distraction gets closed
                    decision["result"] = "deny"
                    def safe_error_clear():
                        try:
                            if win.winfo_exists():
                                typing_var.set("")
                                send_btn.config(state="normal")
                                entry.config(state="normal")
                                _add_message("mojo", "Error talking to AI — closing it anyway.")
                        except Exception:
                            pass
                    win.after(0, safe_error_clear)
                    win.after(1500, lambda: _resolve(-1))

            threading.Thread(target=_run, daemon=True).start()

        def _resolve(duration_minutes: int = 1):
            try:
                if not win.winfo_exists():
                    return
                win.destroy()
            except Exception:
                pass
            
            try:
                # CRITICAL: Grant and Close are MUTUALLY EXCLUSIVE
                if decision["result"] == "grant":
                    # GRANT: Give break, DO NOT close
                    print(f"[_resolve] ✓ GRANTING {duration_minutes}min break - APP STAYS OPEN")
                    if on_valid_reason:
                        on_valid_reason(duration_minutes)
                elif decision["result"] in ("close", "deny") or duration_minutes == -1:
                    # CLOSE/DENY: Close the app, DO NOT grant break
                    print(f"[_resolve] ✗ DENYING - CLOSING distraction")
                    if on_invalid:
                        on_invalid(target_exe, target_hwnd)
                else:
                    print(f"[_resolve] WARNING: No decision made: {decision.get('result')}")
            except Exception as e:
                print(f"[_resolve] Callback error: {e}")
                import traceback
                traceback.print_exc()
            
            try:
                if on_close:
                    on_close()
            except Exception:
                pass

        def _send(event=None):
            msg = entry.get().strip()
            if not msg:
                return
            user_turns["count"] += 1
            entry.delete(0, "end")
            _add_message("user", msg)
            _llm_reply(msg)

        send_btn.config(command=_send)
        entry.bind("<Return>", _send)



        # ── Open with Mojo's first message ────────────────────────────────────
        opening = (
            f"Yo, I caught you on {target_exe or 'something'} 👀\n"
            f"What's the reason?"
        )
        if ocr_text.strip():
            opening += f"\n\nFrom what I saw: {ocr_text[:300]}..."
        _add_message("mojo", opening)
        chat_history.append({"role": "assistant", "parts": [{"text": opening}]})

        # ── Position attached to orb ───────────────────────────────────────────
        win.update_idletasks()
        orb_x = self.root.winfo_x()
        orb_y = self.root.winfo_y()
        orb_width = self.root.winfo_width()
        orb_height = self.root.winfo_height()
        chat_width = 550
        chat_height = 700

        # Place above the orb, centered horizontally
        chat_x = orb_x + (orb_width // 2) - (chat_width // 2)
        chat_y = orb_y - chat_height

        # If not enough space above, place below
        if chat_y < 0:
            chat_y = orb_y + orb_height

        offset_x = chat_x - orb_x
        offset_y = chat_y - orb_y

        win.geometry(f"{chat_width}x{chat_height}+{chat_x}+{chat_y}")

        # Bind to orb movement
        def _update_chat_position(event=None):
            if win.winfo_exists():
                new_orb_x = self.root.winfo_x()
                new_orb_y = self.root.winfo_y()
                new_chat_x = new_orb_x + offset_x
                new_chat_y = new_orb_y + offset_y
                win.geometry(f"{chat_width}x{chat_height}+{new_chat_x}+{new_chat_y}")

        self.root.bind('<Configure>', _update_chat_position)

        win.protocol("WM_DELETE_WINDOW", lambda: None)

        return win

    # ── Orb animation ──────────────────────────────────────────────────────────

    def _tick(self):
        self._draw_orb()
        self._update_timer()
        self._t += 1
        self.root.after(33, self._tick)

    def _draw_orb(self):
        cfg = STATE_PULSE.get(self._state, STATE_PULSE["LOCKED IN"])
        rgb = STATE_COLORS.get(self._state, (168, 85, 247))
        CX  = CY = self.ORB_SIZE // 2

        pulse = 1.0 + math.sin(self._t * cfg["speed"] * math.pi * 2) * cfg["pulse"]
        R     = int(self.ORB_RADIUS * pulse)

        self.canvas.delete("all")

        for i in range(3):
            self._ring_phases[i] += cfg["speed"] * 0.38
            if self._ring_phases[i] > 1.0:
                self._ring_phases[i] -= 1.0
            p  = self._ring_phases[i]
            rr = R + int(p * 20)
            a  = (1.0 - p) * 0.55
            self.canvas.create_oval(CX-rr, CY-rr, CX+rr, CY+rr,
                                    outline=self._blend(rgb, a), width=1)

        hr = int(R * 1.7)
        self.canvas.create_oval(CX-hr, CY-hr, CX+hr, CY+hr,
                                fill=self._blend(rgb, 0.22), outline="")

        self.canvas.create_oval(CX-R, CY-R, CX+R, CY+R,
                                fill=self._blend(rgb, 1.0),
                                outline=self._blend(self._lighten(rgb, 70), 1.0),
                                width=1)

        sr = int(R * 0.55)
        self.canvas.create_oval(CX-sr, CY-sr, CX+sr, CY+sr,
                                fill=self._blend(self._lighten(rgb, 55), 0.45),
                                outline="")

        hr2 = max(3, int(R * 0.30))
        hx  = CX - int(R * 0.27)
        hy  = CY - int(R * 0.28)
        self.canvas.create_oval(hx-hr2, hy-hr2, hx+hr2, hy+hr2,
                                fill="#ffffff", outline="")

    def _update_timer(self):
        """Update or show/hide grace period timer popup window."""
        if not self.app:
            return

        current_time = time.time()
        is_grace_active = self.app.grace_period_until > current_time

        # Hide timer if grace period expired
        if not is_grace_active:
            if self.timer_window:
                try:
                    self._timer_fade_out()
                except Exception:
                    pass
            return

        # Compute remaining time text
        remaining = max(0, self.app.grace_period_until - current_time)
        mins = int(remaining) // 60
        secs = int(remaining) % 60
        timer_text = f"⏱ {mins}:{secs:02d}"

        # Build the minimal pill on first call
        if not self.timer_window:
            self._timer_total   = remaining
            self._timer_drag_dx = 0
            self._timer_drag_dy = 0
            self._timer_detached = False

            tw = tk.Toplevel(self.root)
            tw.overrideredirect(True)
            tw.attributes("-topmost", True)
            tw.attributes("-alpha", 0.0)
            tw.config(bg="#111318")
            self.timer_window = tw

            self._timer_label = tk.Label(
                tw,
                text=timer_text,
                font=("Segoe UI", 10),
                fg="#94a3b8",
                bg="#111318",
                padx=10, pady=4,
            )
            self._timer_label.pack()

            # Drag support
            def _td_start(e):
                self._timer_drag_dx = e.x
                self._timer_drag_dy = e.y
            def _td_move(e):
                nx = tw.winfo_x() + e.x - self._timer_drag_dx
                ny = tw.winfo_y() + e.y - self._timer_drag_dy
                tw.geometry(f"+{nx}+{ny}")
                self._timer_detached = True
            self._timer_label.bind("<Button-1>",  _td_start)
            self._timer_label.bind("<B1-Motion>", _td_move)

            self._timer_fade_in()

        try:
            if not self.timer_window.winfo_exists():
                self.timer_window = None
                return

            # Update text
            self._timer_label.config(text=timer_text)

            # Snap above orb unless user dragged it somewhere
            if not self._timer_detached:
                tw = self.timer_window
                tw.update_idletasks()
                pw = tw.winfo_reqwidth()
                orb_x = self.root.winfo_x()
                orb_y = self.root.winfo_y()
                orb_w = self.root.winfo_width()
                tx = orb_x + (orb_w - pw) // 2
                ty = orb_y - tw.winfo_reqheight() - 6
                tw.geometry(f"+{tx}+{ty}")

        except Exception:
            pass



    def _timer_fade_in(self, alpha=0.0):
        try:
            if self.timer_window and self.timer_window.winfo_exists():
                alpha = min(alpha + 0.08, 0.95)
                self.timer_window.attributes("-alpha", alpha)
                if alpha < 0.95:
                    self.root.after(20, lambda: self._timer_fade_in(alpha))
        except Exception:
            pass

    def _timer_fade_out(self, alpha=None):
        try:
            if alpha is None:
                alpha = float(self.timer_window.attributes("-alpha")) if self.timer_window else 0.0
            if self.timer_window and self.timer_window.winfo_exists() and alpha > 0:
                alpha = max(0.0, alpha - 0.1)
                self.timer_window.attributes("-alpha", alpha)
                self.root.after(20, lambda: self._timer_fade_out(alpha))
            else:
                if self.timer_window:
                    try:
                        self.timer_window.destroy()
                    except Exception:
                        pass
                    self.timer_window = None
                    self._timer_detached = False
        except Exception:
            if self.timer_window:
                try:
                    self.timer_window.destroy()
                except Exception:
                    pass
                self.timer_window = None

    # ── Speech bubbles ─────────────────────────────────────────────────────────

    def _push_bubble(self, message: str):
        bw = tk.Toplevel(self.root)
        bw.overrideredirect(True)
        bw.attributes("-topmost", True)
        bw.attributes("-alpha", 0.0)
        bw.config(bg="#2c2c2e")

        card = tk.Frame(bw, bg="#2c2c2e", padx=18, pady=14)
        card.pack()

        tk.Label(card, text=message, wraplength=260,
                 font=("Segoe UI", 13), fg="#f5f5f7",
                 bg="#2c2c2e", justify="left").pack(anchor="w")

        bw.update_idletasks()
        self._bubble_wins.append((bw, time.time()))
        self._restack_bubbles()
        self._fade(bw, 0.0, 0.92)
        self.root.after(5000, lambda: self._fade_out_and_remove(bw))

    def _fade(self, win, current, target, step=0.07):
        try:
            if current < target:
                current = min(current + step, target)
                win.attributes("-alpha", current)
                if current < target:
                    self.root.after(20, lambda: self._fade(win, current, target, step))
        except Exception:
            pass

    def _fade_out_and_remove(self, bw):
        def _step(alpha):
            try:
                if alpha > 0:
                    bw.attributes("-alpha", alpha)
                    self.root.after(20, lambda: _step(round(alpha - 0.08, 2)))
                else:
                    bw.destroy()
                    self._bubble_wins = [(w, t) for w, t in self._bubble_wins if w is not bw]
                    self._restack_bubbles()
            except Exception:
                self._bubble_wins = [(w, t) for w, t in self._bubble_wins if w is not bw]
        _step(0.92)

    def _restack_bubbles(self):
        try:
            sw = self.root.winfo_screenwidth()
        except Exception:
            sw = 1920
        y = BUBBLE_TOP_START
        for bw, _ in self._bubble_wins:
            try:
                bw.update_idletasks()
                bw_w = bw.winfo_reqwidth()
                bw_h = bw.winfo_reqheight()
                bw.geometry(f"+{sw - bw_w - BUBBLE_RIGHT_MARGIN}+{y}")
                y += bw_h + BUBBLE_GAP
            except Exception:
                pass

    # ── Colour helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _lighten(rgb, amt=70):
        return tuple(min(255, c + amt) for c in rgb)

    def _blend(self, rgb, alpha=1.0):
        bg = (0, 0, 1)
        r  = int(rgb[0] * alpha + bg[0] * (1 - alpha))
        g  = int(rgb[1] * alpha + bg[1] * (1 - alpha))
        b  = int(rgb[2] * alpha + bg[2] * (1 - alpha))
        return f"#{r:02x}{g:02x}{b:02x}"