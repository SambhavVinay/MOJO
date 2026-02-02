import mss
import ollama
import time

def take_screenshot():
    with mss.mss() as sct:
        sct.shot(output="screen.png")

def analyze_screen():
    prompt = """
    You are a productivity monitor. Look at this screenshot and categorize activity:
    
    1. PRODUCTIVE: Code editors (Cursor, VS Code), Terminals, technical documentation, or research papers.
    2. DISTRACTED: YouTube (except tutorials), Reddit, Social Media, Netflix, or Games.
    3. IDLE: Desktop wallpaper or unclear.

    Respond with ONLY: PRODUCTIVE, DISTRACTED, or IDLE.
    """
    
    response = ollama.chat(
        model='llava',
        messages=[{'role': 'user', 'content': prompt, 'images': ['screen.png']}],
        options={'temperature': 0}
    )
    
    return response['message']['content'].strip().upper()

print("Mojo Engine Started. Press Ctrl+C to stop.")
while True:
    take_screenshot()
    status = analyze_screen()
    
    if "PRODUCTIVE" in status:
        print("✅ Sambhav is locked in.")
    elif "DISTRACTED" in status:
        print("🚨 STEP AWAY FROM THE DISTRACTION.")
    else:
        print("💤 Standing by...")

    time.sleep(10)