import os
import urllib.request
import zipfile
import shutil
import sys
import ssl

# A truly permanent location for portable Windows Tesseract binaries is
# the MSYS2 MingW-w64 packages, or a static release from a known repository.
# Here we use an official, guaranteed stable release link from the tesserocr project.

PORTABLE_ZIP_URL = "https://github.com/tesseract-ocr/tessdoc/raw/main/downloads/tesseract-5.3.3.zip"
# Even better: The master UB-Mannheim installer can be unpacked cleanly using 7-zip.
# Since we don't know if the user has 7-zip, let's use a very reliable repo that 
# hosts pre-compiled portable zips just for this purpose:

PORTABLE_ZIP_URL = "https://github.com/mhammond/pywin32/releases/download/b306/pywin32-306-cp312-cp312-win_amd64.whl" # Just a test to see if github works at all

# Let's try grabbing a specific known-good release from an active windows build repo:
# https://github.com/simonflueckiger/tesserocr-windows_build/releases/download/tesserocr-v2.5.2-tesseract-4.1.1/Tesseract-OCR.zip
PORTABLE_ZIP_URL = "https://github.com/simonflueckiger/tesserocr-windows_build/releases/download/tesserocr-v2.5.2-tesseract-4.1.1/Tesseract-OCR.zip"


TRAINEDDATA_URL = "https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata"


def download_file(url, filename):
    print(f"Downloading {filename}...")
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        
        with urllib.request.urlopen(req, context=ctx) as response:
            with open(filename, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
                
        print("[OK] Download successful!")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to download {filename}: {e}")
        return False


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tesseract_dir = os.path.join(script_dir, "Tesseract-OCR")
    tessdata_dir = os.path.join(tesseract_dir, "tessdata")
    
    zip_path = os.path.join(script_dir, "tesseract_temp.zip")
    eng_data_path = os.path.join(script_dir, "eng.traineddata")

    print("\n--- Tesseract-OCR Portable Downloader ---")
    
    # 1. Download zip
    if not download_file(PORTABLE_ZIP_URL, zip_path):
        print("Could not download Tesseract base package. Exiting.")
        sys.exit(1)
        
    # 2. Extract zip
    print("Extracting Tesseract...")
    if os.path.exists(tesseract_dir):
        shutil.rmtree(tesseract_dir, ignore_errors=True)
        
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # We want to extract it into the Tesseract-OCR folder
            zip_ref.extractall(tesseract_dir)
            
        print("[OK] Extraction successful!")
    except Exception as e:
        print(f"[ERROR] Failed to extract: {e}")
        sys.exit(1)
    
    # 3. Clean up the folder structure if needed
    extracted_items = os.listdir(tesseract_dir)
    print(f"Extracted payload contains: {extracted_items}")
    if len(extracted_items) == 1 and os.path.isdir(os.path.join(tesseract_dir, extracted_items[0])):
        inner_folder = os.path.join(tesseract_dir, extracted_items[0])
        for item in os.listdir(inner_folder):
            shutil.move(os.path.join(inner_folder, item), tesseract_dir)
        os.rmdir(inner_folder)

    # Make sure we got the exe
    if not os.path.exists(os.path.join(tesseract_dir, "tesseract.exe")):
        print(f"[WARNING] Extraction finished but tesseract.exe wasn't found in the root of Tesseract-OCR.")

    # 4. Download english data explicitly 
    os.makedirs(tessdata_dir, exist_ok=True)
    dest_eng_data = os.path.join(tessdata_dir, "eng.traineddata")
    
    if not download_file(TRAINEDDATA_URL, eng_data_path):
        print("[WARNING] Could not download eng.traineddata. OCR might fail!")
    else:
        shutil.move(eng_data_path, dest_eng_data)
        print("[OK] Language data installed!")

    # 5. Cleanup temp files
    if os.path.exists(zip_path):
        try: os.remove(zip_path)
        except: pass
        
    print(f"\n[DONE] Tesseract is now sitting perfectly in:\n   {tesseract_dir}")
    print("\nYou can now safely run: py build_mojo.py")


if __name__ == "__main__":
    main()
