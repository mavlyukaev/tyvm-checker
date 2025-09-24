import subprocess
import sys
import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

SCRIPT_PATH = "tyvm_pricebot.py"

# ----------------------
# Логирование
# ----------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
class ReloadHandler(FileSystemEventHandler):
    def __init__(self):
        self.process = None
        self.start_script()

    def start_script(self):
        if self.process:
            logging.info("Остановка текущего процесса бота...")
            self.process.kill()
            self.process.wait()
        logging.info(f"Запуск {SCRIPT_PATH}...")
        self.process = subprocess.Popen([sys.executable, SCRIPT_PATH])
        logging.info("Бот запущен!")

    def on_modified(self, event):
        if event.src_path.endswith(SCRIPT_PATH):
            logging.info(f"{SCRIPT_PATH} изменен, перезапуск бота...")
            self.start_script()

if __name__ == "__main__":
    event_handler = ReloadHandler()
    observer = Observer()
    observer.schedule(event_handler, ".", recursive=False)
    observer.start()
    logging.info("Наблюдение за изменениями запущено...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Прерывание пользователем, остановка наблюдения...")
        observer.stop()
        if event_handler.process:
            event_handler.process.kill()
    observer.join()
    logging.info("Наблюдение завершено.")
