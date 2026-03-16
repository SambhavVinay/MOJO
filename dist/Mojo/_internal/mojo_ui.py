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
import random
import time
import threading
import ollama


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
CHAT_SYSTEM = """You are Mojo, a strict but fair productivity coach.
The user was caught doing something distracting (not related to their stated goal).
Your job is to chat briefly and decide if their reason is valid.

Rules:
- Be concise and direct. Aim for 1-2 short sentences per reply.
- Use a firm tone; don't be overly nice or lenient.
- If they ask for a break, decide if the reason is valid and grant a duration (up to 20 minutes).
- Always end your final reply with one of these tags: [GRANT_ACCESS n] or [DENY_ACCESS].
  - For example: [GRANT_ACCESS 5] means grant 5 minutes.
  - If you grant access but do not provide a duration, the system will default to 1 minute.
- Do not show these tags to the user — they are hidden signals.
- If the user's reason is clearly work-related (tutorial, research, docs, bug fix, class, debugging), grant access.
- If it is clearly entertainment, procrastination, or off-topic, deny access immediately.
- If unsure, deny access to encourage focus.
- Keep the conversation short (max 3 user turns).
- Be stricter: don't grant grace for vague or bullshit reasons.
"""


class MojoUI:
    ORB_SIZE   = 80
    ORB_RADIUS = 22

    def __init__(self, root: tk.Tk, bg_color: str = "#000001"):
        self.root     = root
        self.bg_color = bg_color

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
        win.configure(bg="#1c1c1e")

        # Outer border
        outer = tk.Frame(win, bg="#2a2a2e", padx=1, pady=1)
        outer.pack(fill="both", expand=True)

        inner = tk.Frame(outer, bg="#1c1c1e")
        inner.pack(fill="both", expand=True)

        # Coloured top bar
        tk.Frame(inner, bg=accent, height=4).pack(fill="x")

        # ── Header ────────────────────────────────────────────────────────────
        header = tk.Frame(inner, bg="#1c1c1e", padx=14, pady=10)
        header.pack(fill="x")

        avatar = tk.Frame(header, bg="#1c1c1e", width=34, height=34)
        avatar.pack(side="left", padx=(0, 10))
        avatar.pack_propagate(False)
        tk.Label(avatar, text="🤖", font=("Segoe UI", 16),
                 bg="#1c1c1e").place(relx=0.5, rely=0.5, anchor="center")

        title_col = tk.Frame(header, bg="#1c1c1e")
        title_col.pack(side="left")
        tk.Label(title_col, text="Mojo",
                 font=("Segoe UI", 12, "bold"), fg="#f4f4f5",
                 bg="#1c1c1e").pack(anchor="w")
        tk.Label(title_col, text=f"Caught: {target_exe or 'unknown'}",
                 font=("Segoe UI", 9), fg="#52525b",
                 bg="#1c1c1e").pack(anchor="w")

        tk.Frame(inner, bg="#2a2a2e", height=1).pack(fill="x")

        # ── Chat area (scrollable) ─────────────────────────────────────────────
        chat_frame = tk.Frame(inner, bg="#1c1c1e")
        chat_frame.pack(fill="both", expand=True, padx=0, pady=0)

        scrollbar = tk.Scrollbar(chat_frame, bg="#1c1c1e", troughcolor="#1c1c1e",
                                 highlightthickness=0, bd=0)
        scrollbar.pack(side="right", fill="y")

        chat_canvas = tk.Canvas(chat_frame, bg="#1c1c1e", width=340, height=240,
                                highlightthickness=0, yscrollcommand=scrollbar.set)
        chat_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=chat_canvas.yview)

        msg_frame = tk.Frame(chat_canvas, bg="#1c1c1e")
        chat_canvas.create_window((0, 0), window=msg_frame, anchor="nw", width=340)

        def _on_frame_configure(e):
            chat_canvas.configure(scrollregion=chat_canvas.bbox("all"))
            chat_canvas.yview_moveto(1.0)

        msg_frame.bind("<Configure>", _on_frame_configure)

        # ── Typing indicator ──────────────────────────────────────────────────
        typing_var = tk.StringVar(value="")
        typing_lbl = tk.Label(inner, textvariable=typing_var,
                              font=("Segoe UI", 9), fg="#52525b",
                              bg="#1c1c1e", anchor="w", padx=14)
        typing_lbl.pack(fill="x")

        # ── Input row ─────────────────────────────────────────────────────────
        tk.Frame(inner, bg="#2a2a2e", height=1).pack(fill="x")

        input_row = tk.Frame(inner, bg="#1c1c1e", padx=12, pady=10)
        input_row.pack(fill="x")

        entry_wrap = tk.Frame(input_row, bg="#27272a",
                              highlightthickness=1,
                              highlightbackground="#3f3f46",
                              highlightcolor=accent)
        entry_wrap.pack(side="left", fill="x", expand=True, padx=(0, 8))

        entry = tk.Entry(entry_wrap, font=("Segoe UI", 11),
                         bg="#27272a", fg="#f4f4f5",
                         insertbackground="#f4f4f5",
                         relief="flat", bd=7)
        entry.pack(fill="x")
        entry.focus_set()

        send_btn = tk.Button(input_row, text="↑",
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

            bubble = tk.Label(
                row,
                text=text,
                wraplength=220,
                font=("Segoe UI", 11),
                fg="#f4f4f5" if is_mojo else "#ffffff",
                bg="#27272a" if is_mojo else accent,
                justify="left",
                padx=12, pady=8,
            )

            if is_mojo:
                bubble.pack(anchor="w")
            else:
                bubble.pack(anchor="e")

        # ── LLM reply logic ───────────────────────────────────────────────────
        decision = {"result": None}   # "grant" or "deny"
        user_turns = {"count": 0}

        def _llm_reply(user_msg: str):
            typing_var.set("Mojo is typing...")
            send_btn.config(state="disabled")
            entry.config(state="disabled")

            def _run():
                chat_history.append({"role": "user", "content": user_msg})

                messages = [{"role": "system", "content": CHAT_SYSTEM}] + chat_history

                try:
                    resp    = ollama.chat(model="llama3", messages=messages)
                    raw     = resp["message"]["content"]

                    def _parse_duration_minutes(text: str) -> int:
                        # Find a number (minutes) in the response. Cap to 20.
                        m = re.search(r"(\d+)\s*(min|mins|minutes)?", text, re.IGNORECASE)
                        if m:
                            try:
                                val = int(m.group(1))
                                return max(1, min(val, 20))
                            except Exception:
                                pass
                        return 1

                    duration_mins = _parse_duration_minutes(raw)
                    # Hide internal tags from the user view
                    visible = re.sub(r"\[GRANT_ACCESS.*?\]", "", raw, flags=re.IGNORECASE).strip()
                    visible = re.sub(r"\[DENY_ACCESS\]", "", visible, flags=re.IGNORECASE).strip()

                    chat_history.append({"role": "assistant", "content": raw})

                    win.after(0, lambda: _add_message("mojo", visible))
                    win.after(0, lambda: typing_var.set(""))
                    win.after(0, lambda: send_btn.config(state="normal"))
                    win.after(0, lambda: entry.config(state="normal"))
                    win.after(0, lambda: entry.focus_set())

                    # Check for explicit decision tags
                    if "[GRANT_ACCESS" in raw.upper():
                        decision["result"] = "grant"
                        win.after(1500, lambda: _resolve(duration_mins))
                    elif "[DENY_ACCESS]" in raw.upper():
                        decision["result"] = "deny"
                        win.after(1500, _resolve)
                    else:
                        # If the model didn't include a tag, infer intent from phrasing.
                        low = raw.lower()
                        if "grant" in low and "access" in low:
                            decision["result"] = "grant"
                            print("MojoUI: inferred grant from response")
                            win.after(1500, lambda: _resolve(duration_mins))
                        elif "deny" in low or "no" in low or "dont" in low or "don\'t" in low:
                            # Avoid false negatives by requiring a clear negative.
                            if "access" in low or "permission" in low or "close" in low or "work" in low:
                                decision["result"] = "deny"
                                print("MojoUI: inferred deny from response")
                                win.after(1500, _resolve)

                    # Hard cap: if user has already replied 3 times and
                    # LLM still hasn't granted access, auto-deny.
                    if user_turns["count"] >= 3 and decision["result"] is None:
                        print("MojoUI: max turns reached, auto-deny.")
                        decision["result"] = "deny"
                        win.after(800, _resolve)

                except Exception as e:
                    print(f"Chat LLM error: {e}")
                    win.after(0, lambda: typing_var.set(""))
                    win.after(0, lambda: send_btn.config(state="normal"))
                    win.after(0, lambda: entry.config(state="normal"))

            threading.Thread(target=_run, daemon=True).start()

        def _resolve(duration_minutes: int = 1):
            win.destroy()
            if decision["result"] == "grant":
                if on_valid_reason:
                    on_valid_reason(duration_minutes)
            else:
                if on_invalid:
                    on_invalid(target_exe, target_hwnd)
            if on_close:
                on_close()

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
            f"That's not on your goal list. What's the reason?"
        )
        if ocr_text.strip():
            opening += f"\n\nFrom what I saw on screen: {ocr_text[:500]}..."
        _add_message("mojo", opening)
        chat_history.append({"role": "assistant", "content": opening})

        # ── Centre on screen ──────────────────────────────────────────────────
        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        ww = win.winfo_reqwidth()
        wh = win.winfo_reqheight()
        win.geometry(f"360x420+{(sw - 360) // 2}+{(sh - 420) // 2}")
        win.protocol("WM_DELETE_WINDOW", lambda: None)

        return win

    # ── Orb animation ──────────────────────────────────────────────────────────

    def _tick(self):
        self._draw_orb()
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