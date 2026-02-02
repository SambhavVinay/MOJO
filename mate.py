import tkinter as tk

class MojoPet:
    def __init__(self):
        self.root = tk.Tk()
        
        # 1. Title of the window (hidden)
        self.root.title("Mojo")
        
        # 2. Make it frameless (no close/minimize buttons)
        self.root.overrideredirect(True)
        
        # 3. Always stay on top of other windows
        self.root.attributes("-topmost", True)
        
        # 4. Set the size and position (Bottom Right)
        # Format: Width x Height + X_Offset + Y_Offset
        self.root.geometry("200x200+1300+700")

        # 5. Make it transparent-ish (Windows specific)
        self.root.config(bg='grey')
        self.root.attributes("-alpha", 0.8) # 80% solid

        # Add a simple text label to act as our "Pet" for now
        self.label = tk.Label(self.root, text="👁️", font=("Arial", 80), bg='grey', fg='white')
        self.label.pack(expand=True)

        print("Mate UI is running. Press Alt+F4 to kill it if you get stuck!")
        self.root.mainloop()

if __name__ == "__main__":
    MojoPet()