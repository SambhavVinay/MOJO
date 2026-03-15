# Mojo — Deployment Guide

Follow these steps to package and share Mojo with someone else.

---

## Step 1: Build the app

From the project folder, run:

```bash
python build_mojo.py
```

This creates a `dist\Mojo\` folder containing the executable and dependencies.

---

## Step 2: Include the Tesseract folder (portable OCR)

For OCR (tab/window text) to work without installing Tesseract system-wide:

1. Install [Tesseract for Windows](https://github.com/UB-Mannheim/tesseract/wiki) or copy an existing install.
2. Place a **`tesseract`** folder next to the Mojo executable:
   - Either copy the whole `Tesseract-OCR` install folder and rename it to **`tesseract`**,
   - Or create a folder named **`tesseract`** and put **`tesseract.exe`** (and its data/tessdata) inside it.

Your friend can also install Tesseract in `C:\Program Files\Tesseract-OCR`; the app will use that if no local `tesseract` folder is found.

---

## Step 3: Zip and send

1. Zip the entire **`dist\Mojo`** folder (including the `tesseract` folder if you added it).
2. Send the zip (e.g. Mojo.zip) to your friend.
3. They should:
   - Unzip to a folder (e.g. `Desktop\Mojo`).
   - Run **`Mojo.exe`**.
   - Enter their **Gemini API key** when prompted (it is saved in `config.json` in the same folder for next time).

No Python or extra installs are required on their machine beyond the contents of the zip and, if you didn’t bundle it, a system Tesseract install.
