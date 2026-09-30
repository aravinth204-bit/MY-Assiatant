import os
import subprocess
import sys

def build():
    print("Building ARAVI-ASSISTANT single portable .exe using PyInstaller...")

    add_data_sep = ";" if sys.platform.startswith("win") else ":"

    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onedir",  # or --onefile
        "--windowed",
        "--name=ARAVI-ASSISTANT",
        f"--add-data=assets{add_data_sep}assets",
        f"--add-data=ui{add_data_sep}ui",
        "main.py"
    ]

    print("Running command:", " ".join(cmd))
    res = subprocess.run(cmd)
    if res.returncode == 0:
        print("\n✅ Build succeeded! Executable generated in 'dist/ARAVI-ASSISTANT/ARAVI-ASSISTANT.exe'")
    else:
        print("\n❌ Build failed. Make sure pyinstaller is installed ('pip install pyinstaller').")

if __name__ == "__main__":
    build()
