# Shitty Archive Bruteforcer

A simple, cross-platform Python GUI tool for brute-forcing 7zip, zip, and rar archive passwords.

## Features
- Multi-threaded brute force for 7z, zip, rar
- Easy-to-use PyQt5 GUI
- Help dialog with donation/book links
- Github-friendly structure and minimal dependencies

## Usage
1. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```
2. Run:
   ```sh
   python main.py
   ```

## Build (Standalone EXE)
1. Install Nuitka:
   ```sh
   pip install nuitka
   ```
2. Build:
   ```sh
   python -m nuitka --standalone --enable-plugin=pyqt5 --windows-icon-from-ico=appicon.ico --windows-disable-console --output-dir=release_nuitka main.py
   ```
3. Copy these files to the EXE directory:
   - `dictionary.txt`
   - `appicon.ico`
   - `question.svg`, `paypal.svg`, `book.svg`, `amazon_a.svg`

## Repo Structure
```
ShittyBruteForcer/
├── main.py
├── bruteforce.py
├── requirements.txt
├── dictionary.txt
├── appicon.ico
├── question.svg
├── paypal.svg
├── book.svg
├── amazon_a.svg
├── README.md
├── .gitignore
```

## License
MIT
