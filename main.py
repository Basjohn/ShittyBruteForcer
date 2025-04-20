import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
import sys
import os
import json
import time
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtWidgets import QFileDialog, QMessageBox, QProgressBar, QCheckBox, QSpinBox
from bruteforce import BruteForceConfig, BruteForceWorker
import multiprocessing
import math
import subprocess

def get_app_icon_path():
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, "appicon.ico")
    return os.path.join(os.path.dirname(__file__), "appicon.ico")

APP_ICON_PATH = get_app_icon_path()
SUCCESS_LOG = os.path.join(os.path.dirname(__file__), "success.log")

class PasswordBruteForceApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Shitty Archive Bruteforcer (Python Edition)")
        self.setWindowIcon(QtGui.QIcon(APP_ICON_PATH))
        self.setMinimumSize(600, 420)
        self.setStyleSheet("""
            QMainWindow { background: #f8f9fa; }
            QLabel, QLineEdit, QPushButton, QCheckBox {
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13pt;
            }
            QPushButton {
                background: #e9ecef;
                border-radius: 8px;
                padding: 8px 18px;
                border: 1px solid #ced4da;
            }
            QPushButton:hover {
                background: #dee2e6;
            }
        """)
        self.worker = None
        self.paused = False
        self.archive_path = None
        self.resume_log_path = None
        self.last_attempted_length = None
        self.last_attempted_password = None
        self.last_gui_update = 0
        self.last_attempted_string = ""
        self.pause_event = multiprocessing.Event()
        self.init_ui()
        # Enable drag and drop
        self.setAcceptDrops(True)

    def init_ui(self):
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(18)

        self.file_label = QtWidgets.QLabel("Archive file:")
        layout.addWidget(self.file_label)
        file_row = QtWidgets.QHBoxLayout()
        self.file_edit = QtWidgets.QLineEdit()
        self.file_edit.setPlaceholderText("Select an archive file (.zip, .rar, .7z)")
        file_row.addWidget(self.file_edit)
        self.browse_btn = QtWidgets.QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.browse_file)
        file_row.addWidget(self.browse_btn)
        layout.addLayout(file_row)

        self.min_length_edit = QSpinBox()
        self.min_length_edit.setMinimum(1)
        self.min_length_edit.setMaximum(32)
        self.min_length_edit.setValue(4)
        self.max_length_edit = QSpinBox()
        self.max_length_edit.setMinimum(1)
        self.max_length_edit.setMaximum(32)
        self.max_length_edit.setValue(6)
        length_row = QtWidgets.QHBoxLayout()
        length_row.addWidget(QtWidgets.QLabel("Min length:"))
        length_row.addWidget(self.min_length_edit)
        length_row.addWidget(QtWidgets.QLabel("Max length:"))
        length_row.addWidget(self.max_length_edit)
        layout.addLayout(length_row)

        options_layout = QtWidgets.QVBoxLayout()
        self.minimal_strain_chk = QCheckBox("Minimal Strain (4 cores, 8GB max)")
        options_layout.addWidget(self.minimal_strain_chk)
        self.symbols_chk = QCheckBox("Symbols")
        self.symbols_chk.setChecked(True)
        options_layout.addWidget(self.symbols_chk)
        dict_row = QtWidgets.QHBoxLayout()
        self.dictionary_btn = QtWidgets.QPushButton("Dictionary")
        self.dictionary_btn.clicked.connect(self.open_dictionary)
        dict_row.addWidget(self.dictionary_btn)
        options_layout.addLayout(dict_row)
        layout.addLayout(options_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(0)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        btn_row = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("Start Brute Force")
        self.start_btn.clicked.connect(self.start_bruteforce)
        btn_row.addWidget(self.start_btn)
        self.pause_btn = QtWidgets.QPushButton("Pause")
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.pause_btn.setEnabled(False)
        btn_row.addWidget(self.pause_btn)
        layout.addLayout(btn_row)

        self.result_label = QtWidgets.QLabel("")
        layout.addWidget(self.result_label)

        # Add help button at bottom right
        help_btn = QtWidgets.QPushButton()
        help_btn.setIcon(QtGui.QIcon(os.path.join(os.path.dirname(__file__), "question.svg")))
        help_btn.setIconSize(QtCore.QSize(22, 22))
        help_btn.setFixedSize(28, 28)
        help_btn.setStyleSheet("border: none; background: transparent;")
        help_btn.setCursor(QtCore.Qt.PointingHandCursor)
        help_btn.clicked.connect(self.show_help_dialog)
        help_layout = QtWidgets.QHBoxLayout()
        help_layout.addStretch()
        help_layout.addWidget(help_btn)
        layout.addLayout(help_layout)

        self.setCentralWidget(central)

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Archive", "", "Archives (*.zip *.rar *.7z)")
        if file_path:
            self.open_archive(file_path)

    def open_archive(self, archive_path):
        self.archive_path = archive_path
        base = os.path.splitext(os.path.basename(self.archive_path))[0]
        exe_dir = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__)
        attempt_log_path = os.path.join(exe_dir, f"{base}.attempts.log")
        resume_from = None
        if os.path.isfile(attempt_log_path):
            # Try to extract last attempted password and length
            try:
                with open(attempt_log_path, "r", encoding="utf-8") as f:
                    last_line = None
                    for line in f:
                        if line.strip():
                            last_line = line.strip()
                    if last_line:
                        if last_line.startswith("dict:"):
                            # If last was a dict attempt, skip to brute-force
                            pass
                        else:
                            # Format: length:password
                            parts = last_line.split(":", 1)
                            if len(parts) == 2:
                                resume_from = (int(parts[0]), parts[1])
            except Exception:
                pass
        if resume_from:
            reply = QMessageBox.question(self, "Continue?", "A previous session was detected for this archive. Do you want to continue from the last attempt?", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.last_attempted_length, self.last_attempted_password = resume_from
            else:
                self.last_attempted_length, self.last_attempted_password = None, None
        else:
            self.last_attempted_length, self.last_attempted_password = None, None
        self.file_edit.setText(archive_path)

    def start_bruteforce(self):
        archive = self.file_edit.text().strip()
        if not archive or not os.path.exists(archive):
            QMessageBox.warning(self, "Input Error", "Please select a valid archive file.")
            return
        # Use open_archive logic for resume
        self.open_archive(archive)
        min_length = self.min_length_edit.value()
        max_length = self.max_length_edit.value()
        resume_from = None
        if self.last_attempted_length is not None and self.last_attempted_password is not None:
            resume_from = (self.last_attempted_length, self.last_attempted_password)
        config = BruteForceConfig(
            min_length=min_length,
            max_length=max_length,
            minimal_strain=self.minimal_strain_chk.isChecked(),
            cuda_enabled=False
        )
        charset = self.get_charset()
        charset_len = len(charset)
        self.total_attempts = 0
        for length in range(min_length, max_length + 1):
            self.total_attempts += charset_len ** length
        exe_dir = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__)
        dict_path = os.path.join(exe_dir, "dictionary.txt")
        if os.path.isfile(dict_path):
            try:
                with open(dict_path, "r", encoding="utf-8", errors="ignore") as f:
                    dict_lines = sum(1 for _ in f)
                self.total_attempts += dict_lines
            except Exception:
                pass
        self.progress_bar.setMaximum(self.total_attempts)
        self.progress_bar.setValue(0)
        self.result_label.setText("Brute-forcing...")
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        QtWidgets.QApplication.processEvents()
        base = os.path.splitext(os.path.basename(self.archive_path))[0]
        attempt_log_path = os.path.join(exe_dir, f"{base}.attempts.log")
        self.worker = BruteForceWorker(
            archive,
            config,
            progress_callback=self.on_progress,
            found_callback=self.on_found,
            pause_event=self.pause_event,
            resume_from=resume_from,
            log_path=attempt_log_path,
            charset=charset
        )
        self.worker.start()

    def get_charset(self):
        import string
        charset = string.ascii_letters + string.digits
        if self.symbols_chk.isChecked():
            charset += string.punctuation
        return charset

    def toggle_pause(self):
        if not self.worker:
            return
        self.paused = not self.paused
        if self.paused:
            self.pause_btn.setText("Resume")
        else:
            self.pause_btn.setText("Pause")
        if hasattr(self.worker, 'set_paused'):
            self.worker.set_paused(self.paused)

    def on_progress(self, attempts, last_string=None):
        now = time.time()
        if now - self.last_gui_update < 3 and attempts != 1:
            return
        self.last_gui_update = now
        if last_string is not None:
            self.last_attempted_string = last_string
        self.progress_bar.setMaximum(self.total_attempts)
        self.progress_bar.setValue(min(attempts, self.total_attempts))
        display = f"Attempts: {attempts:,} | Last: {self.last_attempted_string}"
        self.progress_bar.setFormat(display)
        self.progress_bar.setAlignment(QtCore.Qt.AlignCenter)

    def on_found(self, password):
        self.result_label.setText(f"Password found: <b>{password}</b>")
        # Silent popup with just the password
        QtWidgets.QMessageBox.information(self, "SUCCESS", f"SUCCESS: {password}", QtWidgets.QMessageBox.Ok)
        exe_dir = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__)
        success_log = os.path.join(exe_dir, "Success.txt")
        # Additive logging: insert new entry at the top
        log_entry = f"{self.archive_path}: {password}\n"
        try:
            if os.path.exists(success_log):
                with open(success_log, "r", encoding="utf-8") as f:
                    old_content = f.read()
            else:
                old_content = ""
            with open(success_log, "w", encoding="utf-8") as f:
                f.write(log_entry + old_content)
        except Exception:
            pass
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        # Stop brute-forcing if still running
        if self.worker:
            self.worker.stop()

    def on_log_attempt(self, length, password):
        if self.resume_log_path:
            try:
                with open(self.resume_log_path, "w") as f:
                    json.dump({"last_length": length, "last_password": password}, f)
            except Exception:
                pass
        base = os.path.splitext(os.path.basename(self.archive_path))[0]
        exe_dir = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__)
        attempt_log_path = os.path.join(exe_dir, f"{base}.attempts.log")
        try:
            with open(attempt_log_path, "a", encoding="utf-8") as f:
                f.write(f"{length}:{password}\n")
        except Exception:
            pass

    def open_dictionary(self):
        exe_dir = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__)
        dict_path = os.path.join(exe_dir, "dictionary.txt")
        if not os.path.isfile(dict_path):
            with open(dict_path, "w", encoding="utf-8") as f:
                f.write("")
        # Open with default editor
        try:
            if sys.platform == "win32":
                os.startfile(dict_path)
            else:
                subprocess.Popen(["xdg-open", dict_path])
        except Exception:
            QMessageBox.warning(self, "Error", "Could not open dictionary.txt")

    def show_help_dialog(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("About Shitty Archive Bruteforcer")
        dlg.setFixedWidth(400)
        layout = QtWidgets.QVBoxLayout(dlg)
        label = QtWidgets.QLabel("Made for my own shitty memory, shared freely for yours. You can always donate to my dumbass though or buy my shitty literature.")
        label.setWordWrap(True)
        label.setStyleSheet("font-size: 14px; color: #222;")
        layout.addWidget(label)
        icon_row = QtWidgets.QHBoxLayout()
        # Paypal
        paypal_btn = QtWidgets.QPushButton()
        paypal_btn.setIcon(QtGui.QIcon(os.path.join(os.path.dirname(__file__), "paypal.svg")))
        paypal_btn.setIconSize(QtCore.QSize(28, 28))
        paypal_btn.setFixedSize(34, 34)
        paypal_btn.setStyleSheet("border: none; background: transparent;")
        paypal_btn.setCursor(QtCore.Qt.PointingHandCursor)
        paypal_btn.clicked.connect(lambda: __import__('webbrowser').open("https://www.paypal.com/donate/?business=UBZJY8KHKKLGC&no_recurring=0&item_name=Why+are+you+doing+this?+Are+you+drunk?+&currency_code=USD"))
        icon_row.addWidget(paypal_btn)
        # Goodreads/book
        book_btn = QtWidgets.QPushButton()
        book_btn.setIcon(QtGui.QIcon(os.path.join(os.path.dirname(__file__), "book.svg")))
        book_btn.setIconSize(QtCore.QSize(28, 28))
        book_btn.setFixedSize(34, 34)
        book_btn.setStyleSheet("border: none; background: transparent;")
        book_btn.setCursor(QtCore.Qt.PointingHandCursor)
        book_btn.clicked.connect(lambda: __import__('webbrowser').open("https://www.goodreads.com/book/show/25006763-usu"))
        icon_row.addWidget(book_btn)
        # Amazon
        amazon_btn = QtWidgets.QPushButton()
        amazon_btn.setIcon(QtGui.QIcon(os.path.join(os.path.dirname(__file__), "amazon_a.svg")))
        amazon_btn.setIconSize(QtCore.QSize(28, 28))
        amazon_btn.setFixedSize(34, 34)
        amazon_btn.setStyleSheet("border: none; background: transparent;")
        amazon_btn.setCursor(QtCore.Qt.PointingHandCursor)
        amazon_btn.clicked.connect(lambda: __import__('webbrowser').open("https://www.amazon.com/Usu-Jayde-Ver-Elst-ebook/dp/B00V8A5K7Y"))
        icon_row.addWidget(amazon_btn)
        layout.addLayout(icon_row)
        dlg.exec_()

    def closeEvent(self, event):
        if self.worker:
            self.worker.stop()
        event.accept()
        # Forcefully terminate the process and all children to ensure no lingering resources
        import signal
        import os
        try:
            # On Windows, use os._exit to guarantee process exit
            os._exit(0)
        except Exception:
            pass

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(('.zip', '.rar', '.7z')):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path.lower().endswith(('.zip', '.rar', '.7z')):
                    self.open_archive(file_path)
                    break

def run_gui():
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon(APP_ICON_PATH))
    window = PasswordBruteForceApp()
    window.setWindowIcon(QtGui.QIcon(APP_ICON_PATH))  # Redundant but helps for taskbar
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    # Check py7zr availability
    try:
        import py7zr
    except ImportError:
        QtWidgets.QMessageBox.critical(None, "Missing Dependency", "py7zr is not installed! Please install it using 'pip install py7zr'.")
        sys.exit(1)
    app = QtWidgets.QApplication(sys.argv)
    window = PasswordBruteForceApp()
    window.show()
    sys.exit(app.exec_())
