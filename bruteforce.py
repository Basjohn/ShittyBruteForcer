import itertools
import string
import multiprocessing
import threading
import os
import time
from queue import Empty
import sys
import psutil

CHARSET = string.ascii_letters + string.digits + string.punctuation

def skip_iterator(it, start_value):
    for val in it:
        if val == start_value:
            yield val
            break
    yield from it

def chunked_password_space(length, num_chunks, chunk_idx, charset):
    total = len(charset) ** length
    chunk_size = total // num_chunks
    start = chunk_idx * chunk_size
    end = (chunk_idx + 1) * chunk_size if chunk_idx < num_chunks - 1 else total
    def idx_to_pw(idx):
        pw = []
        for _ in range(length):
            pw.append(charset[idx % len(charset)])
            idx //= len(charset)
        return ''.join(reversed(pw))
    return (idx_to_pw(i) for i in range(start, end))

def try_password_top(archive_path, password):
    import os
    ext = os.path.splitext(archive_path)[1].lower()
    if ext == ".zip":
        import zipfile
        try:
            with zipfile.ZipFile(archive_path) as zf:
                zf.extractall(pwd=password.encode('utf-8'))
            return True
        except Exception:
            return False
    elif ext == ".rar":
        try:
            import rarfile
            with rarfile.RarFile(archive_path) as rf:
                rf.extractall(pwd=password)
            return True
        except Exception:
            return False
    elif ext == ".7z":
        try:
            import py7zr
            with py7zr.SevenZipFile(archive_path, mode='r', password=password) as z:
                z.extractall()
            return True
        except Exception as e:
            # Only log if not the expected invalid block data error
            if "invalid block data" not in str(e).lower():
                with open("7z_debug.log", "a", encoding="utf-8") as dbg:
                    dbg.write(f"Failed password: {password} for {archive_path}\nError: {e}\n")
            # Otherwise, treat as normal failed attempt (do not log)
            return False
    return False

def dictionary_attack(archive_path, dict_path, progress_queue, found_event, stop_flag, log_path, pause_event, archive_drive):
    try:
        with open(dict_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                pw = line.strip()
                if not pw:
                    continue
                if stop_flag.is_set() or found_event.is_set():
                    break
                if pause_event and pause_event.is_set():
                    time.sleep(0.1)
                    continue
                if log_path:
                    try:
                        with open(log_path, "a", encoding="utf-8") as lf:
                            lf.write(f"dict:{pw}\n")
                    except Exception:
                        pass
                progress_queue.put((1, pw))
                if try_password_top(archive_path, pw):
                    found_event.set()
                    progress_queue.put((0, pw))
                    # Write success to SUCCESS.txt
                    try:
                        with open("SUCCESS.txt", "a", encoding="utf-8") as sf:
                            sf.write(f"SUCCESS: {archive_path} | {pw}\n")
                    except Exception:
                        pass
                    break
    except Exception:
        pass

def mp_worker(archive_path, length, num_chunks, chunk_idx, progress_queue, found_event, stop_flag, log_path, pause_event, chunk_resume, archive_drive, charset, minimal_strain=False):
    pw_iter = chunked_password_space(length, num_chunks, chunk_idx, charset)
    if chunk_resume is not None:
        pw_iter = skip_iterator(pw_iter, chunk_resume)
    temp_dir = None
    if archive_drive:
        temp_dir = os.path.join(archive_drive + os.sep, "temp_bruteforce")
        os.makedirs(temp_dir, exist_ok=True)
        os.environ['TMPDIR'] = temp_dir
        os.environ['TEMP'] = temp_dir
        os.environ['TMP'] = temp_dir
    for pw in pw_iter:
        if stop_flag.is_set() or found_event.is_set():
            break
        if pause_event and pause_event.is_set():
            time.sleep(0.1)
            continue
        # Log attempt
        if log_path:
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"{length}:{pw}\n")
            except Exception:
                pass
        # Progress update
        progress_queue.put((1, pw))
        if try_password_top(archive_path, pw):
            found_event.set()
            progress_queue.put((0, pw))  # Signal found
            # Write success to SUCCESS.txt
            try:
                with open("SUCCESS.txt", "a", encoding="utf-8") as sf:
                    sf.write(f"SUCCESS: {archive_path} | {pw}\n")
            except Exception:
                pass
            break
        if minimal_strain:
            time.sleep(0.03)

class BruteForceConfig:
    def __init__(self, min_length=1, max_length=6, minimal_strain=False, cuda_enabled=False):
        self.min_length = min_length
        self.max_length = max_length
        self.minimal_strain = minimal_strain
        self.cuda_enabled = cuda_enabled

class BruteForceWorker:
    def __init__(self, archive_path, config: BruteForceConfig, progress_callback=None, found_callback=None, pause_event=None, resume_from=None, log_path=None, charset=None):
        self.archive_path = archive_path
        self.config = config
        self.progress_callback = progress_callback
        self.found_callback = found_callback
        self.pause_event = pause_event
        self.resume_from = resume_from
        self.stop_flag = multiprocessing.Event()
        # Minimal strain: limit to 4 cores and sleep
        if self.config.minimal_strain:
            self.pool_size = 4
            self.minimal_strain = True
        else:
            self.pool_size = os.cpu_count()
            self.minimal_strain = False
        self.log_path = log_path
        self.progress_thread = None
        self.charset = charset if charset else (string.ascii_letters + string.digits + string.punctuation)
        self.processes = []

    def start(self):
        self.progress_queue = multiprocessing.Queue()
        self.found_event = multiprocessing.Event()
        self.processes = []
        archive_drive = os.path.splitdrive(self.archive_path)[0] or None
        exe_dir = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__)
        dict_path = os.path.join(exe_dir, "dictionary.txt")
        if os.path.isfile(dict_path):
            dict_proc = multiprocessing.Process(target=dictionary_attack, args=(self.archive_path, dict_path, self.progress_queue, self.found_event, self.stop_flag, self.log_path, self.pause_event, archive_drive))
            dict_proc.daemon = True
            dict_proc.start()
            self.processes.append(dict_proc)
            dict_proc.join()  # Wait for dictionary before brute force
            if self.found_event.is_set() or self.stop_flag.is_set():
                return
        for length in range(self.config.min_length, self.config.max_length + 1):
            num_chunks = self.pool_size
            for chunk_idx in range(num_chunks):
                chunk_resume = None
                if self.resume_from and length == self.resume_from[0] and chunk_idx == 0:
                    chunk_resume = self.resume_from[1]
                p = multiprocessing.Process(target=mp_worker,
                                            args=(self.archive_path, length, num_chunks, chunk_idx, self.progress_queue, self.found_event, self.stop_flag, self.log_path, self.pause_event, chunk_resume, archive_drive, self.charset, self.minimal_strain))
                p.daemon = True
                p.start()
                self.processes.append(p)
        self.progress_thread = threading.Thread(target=self._progress_loop, daemon=True)
        self.progress_thread.start()

    def stop(self):
        self.stop_flag.set()
        # Terminate all child processes
        for p in self.processes:
            if p.is_alive():
                p.terminate()
                p.join(timeout=2)
        if self.progress_thread:
            self.progress_thread.join(timeout=2)
        # Clean up queues/events
        try:
            self.progress_queue.close()
        except Exception:
            pass
        try:
            self.found_event.set()
        except Exception:
            pass

    def set_paused(self, paused):
        if self.pause_event:
            if paused:
                self.pause_event.set()
            else:
                self.pause_event.clear()

    def _progress_loop(self):
        attempts = 0
        last_pw = ""
        while True:
            try:
                msg = self.progress_queue.get(timeout=1)
                if msg[0] == 1:
                    attempts += 1
                    last_pw = msg[1]
                    if self.progress_callback:
                        self.progress_callback(attempts, last_pw)
                elif msg[0] == 0:
                    # Found password
                    if self.found_callback:
                        self.found_callback(msg[1])
                    break
            except Empty:
                if self.stop_flag.is_set() or (self.found_event and self.found_event.is_set()):
                    break
