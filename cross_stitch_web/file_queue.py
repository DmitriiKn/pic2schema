# file_queue.py
# Менеджер очереди файлов с автоматической очисткой

import os
import time
import threading
import shutil
import json
from pathlib import Path
from datetime import datetime, timedelta
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FileQueueManager:
    """
    Менеджер очереди файлов с автоматической очисткой
    Поддерживает максимальный размер очереди и время жизни файлов
    """
    
    def __init__(self, upload_dir: str, max_queue_size: int = 100, max_file_age_hours: int = 1):
        """
        Инициализация менеджера очереди
        
        Args:
            upload_dir: директория для загрузок
            max_queue_size: максимальное количество файлов в очереди
            max_file_age_hours: максимальное время жизни файла в часах
        """
        self.upload_dir = upload_dir
        self.max_queue_size = max_queue_size
        self.max_file_age_hours = max_file_age_hours
        self.queue_file = os.path.join(upload_dir, '.file_queue.json')
        self.lock = threading.Lock()
        
        # Создаем директорию, если её нет
        os.makedirs(upload_dir, exist_ok=True)
        
        # Инициализируем очередь
        self.file_queue = self._load_queue()
        
        # Запускаем фоновую очистку
        self._start_cleanup_thread()
    
    def _load_queue(self):
        """Загружает очередь из файла с обработкой ошибок"""
        try:
            if os.path.exists(self.queue_file):
                # Проверяем, не пустой ли файл
                if os.path.getsize(self.queue_file) == 0:
                    logger.warning(f"Файл очереди {self.queue_file} пуст. Создаем новую очередь.")
                    return []
                
                with open(self.queue_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:  # Пустой файл
                        return []
                    
                    data = json.loads(content)
                    # Проверяем, что данные - это список
                    if isinstance(data, list):
                        return data
                    else:
                        logger.warning(f"Неверный формат очереди: ожидался список, получен {type(data)}")
                        return []
            else:
                logger.info(f"Файл очереди {self.queue_file} не найден. Будет создан при первом добавлении.")
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON в {self.queue_file}: {e}")
            # Создаем резервную копию поврежденного файла
            if os.path.exists(self.queue_file):
                backup_name = f"{self.queue_file}.bak.{int(time.time())}"
                try:
                    os.rename(self.queue_file, backup_name)
                    logger.info(f"Поврежденный файл очереди перемещен в {backup_name}")
                except:
                    pass
        except Exception as e:
            logger.error(f"Неожиданная ошибка при загрузке очереди: {e}")
        
        return []
    
    def _save_queue(self):
        """Сохраняет очередь в файл с обработкой ошибок"""
        try:
            # Создаем временный файл для атомарной записи
            temp_file = f"{self.queue_file}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.file_queue, f, indent=2, ensure_ascii=False)
            
            # Атомарно заменяем старый файл новым
            os.replace(temp_file, self.queue_file)
            
        except Exception as e:
            logger.error(f"Ошибка сохранения очереди: {e}")
    
    def _start_cleanup_thread(self):
        """Запускает фоновый поток для очистки"""
        def cleanup_worker():
            logger.info("Поток очистки запущен")
            while True:
                try:
                    # Спим немного перед первой очисткой
                    time.sleep(60)  # Первая проверка через минуту
                    
                    while True:  # Бесконечный цикл внутри потока
                        self.cleanup_old_files()
                        self.enforce_queue_size()
                        time.sleep(300)  # Проверка каждые 5 минут
                        
                except Exception as e:
                    logger.error(f"Ошибка в cleanup_worker: {e}")
                    time.sleep(60)  # При ошибке ждем минуту и пробуем снова
        
        thread = threading.Thread(target=cleanup_worker, daemon=True)
        thread.start()
        logger.info("Запущен поток автоматической очистки файлов")
    
    def add_file(self, file_path: str, file_id: str, file_type: str = "pattern"):
        """
        Добавляет файл в очередь с timestamp
        
        Args:
            file_path: полный путь к файлу
            file_id: уникальный идентификатор файла
            file_type: тип файла (input, pattern, preview)
        
        Returns:
            dict: информация о добавленном файле
        """
        with self.lock:
            # Проверяем, существует ли файл
            if not os.path.exists(file_path):
                logger.error(f"Файл не существует: {file_path}")
                return None
            
            timestamp = time.time()
            file_info = {
                "file_id": file_id,
                "file_path": file_path,
                "file_name": os.path.basename(file_path),
                "file_size": os.path.getsize(file_path),
                "timestamp": timestamp,
                "datetime": datetime.fromtimestamp(timestamp).isoformat(),
                "file_type": file_type
            }
            
            self.file_queue.append(file_info)
            self._save_queue()
            
            # Проверяем размер очереди после добавления
            self.enforce_queue_size()
            
            logger.info(f"Файл добавлен в очередь: {os.path.basename(file_path)} (ID: {file_id}, тип: {file_type})")
            return file_info
    
    def remove_file(self, file_path: str):
        """Удаляет файл и его запись из очереди"""
        with self.lock:
            # Находим запись
            file_info = None
            for f in self.file_queue:
                if f["file_path"] == file_path:
                    file_info = f
                    break
            
            if file_info:
                # Удаляем из очереди
                self.file_queue = [f for f in self.file_queue if f["file_path"] != file_path]
                
                # Удаляем физический файл
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"Файл удален: {os.path.basename(file_path)}")
                except Exception as e:
                    logger.error(f"Ошибка удаления файла {file_path}: {e}")
                
                self._save_queue()
                return True
            return False
    
    def remove_by_file_id(self, file_id: str):
        """Удаляет все файлы с указанным file_id"""
        with self.lock:
            # Находим все файлы с этим ID
            files_to_remove = [f for f in self.file_queue if f["file_id"] == file_id]
            
            if not files_to_remove:
                logger.info(f"Файлы с ID {file_id} не найдены в очереди")
                return 0
            
            # Удаляем физические файлы
            removed_count = 0
            for file_info in files_to_remove:
                try:
                    if os.path.exists(file_info["file_path"]):
                        os.remove(file_info["file_path"])
                        logger.info(f"Файл удален по ID: {os.path.basename(file_info['file_path'])}")
                        removed_count += 1
                except Exception as e:
                    logger.error(f"Ошибка удаления файла {file_info['file_path']}: {e}")
            
            # Удаляем из очереди
            self.file_queue = [f for f in self.file_queue if f["file_id"] != file_id]
            self._save_queue()
            
            logger.info(f"Удалено {removed_count} файлов с ID {file_id}")
            return removed_count
    
    def cleanup_old_files(self):
        """Удаляет файлы старше max_file_age_hours"""
        with self.lock:
            if not self.file_queue:
                return 0
            
            current_time = time.time()
            cutoff_time = current_time - (self.max_file_age_hours * 3600)
            
            # Находим старые файлы
            old_files = [f for f in self.file_queue if f["timestamp"] < cutoff_time]
            
            if not old_files:
                return 0
            
            removed_count = 0
            for file_info in old_files:
                try:
                    if os.path.exists(file_info["file_path"]):
                        age_hours = (current_time - file_info["timestamp"]) / 3600
                        os.remove(file_info["file_path"])
                        logger.info(f"Удален старый файл: {os.path.basename(file_info['file_path'])} (возраст: {age_hours:.1f} ч)")
                        removed_count += 1
                except Exception as e:
                    logger.error(f"Ошибка удаления старого файла {file_info['file_path']}: {e}")
            
            # Обновляем очередь
            self.file_queue = [f for f in self.file_queue if f["timestamp"] >= cutoff_time]
            self._save_queue()
            
            if removed_count > 0:
                logger.info(f"Очистка старых файлов: удалено {removed_count} файлов")
            
            return removed_count
    
    def enforce_queue_size(self):
        """Обеспечивает максимальный размер очереди (удаляет самые старые файлы)"""
        with self.lock:
            if len(self.file_queue) <= self.max_queue_size:
                return 0
            
            # Сортируем по timestamp (самые старые в начале)
            sorted_queue = sorted(self.file_queue, key=lambda x: x["timestamp"])
            
            # Сколько файлов нужно удалить
            files_to_remove_count = len(sorted_queue) - self.max_queue_size
            files_to_remove = sorted_queue[:files_to_remove_count]
            
            removed_count = 0
            for file_info in files_to_remove:
                try:
                    if os.path.exists(file_info["file_path"]):
                        os.remove(file_info["file_path"])
                        logger.info(f"Удален файл из хвоста очереди: {os.path.basename(file_info['file_path'])}")
                        removed_count += 1
                except Exception as e:
                    logger.error(f"Ошибка удаления файла из очереди {file_info['file_path']}: {e}")
            
            # Оставляем только последние max_queue_size файлов
            self.file_queue = sorted_queue[files_to_remove_count:]
            self._save_queue()
            
            if removed_count > 0:
                logger.info(f"Очередь сокращена: удалено {removed_count} файлов")
            
            return removed_count
    
    def get_queue_stats(self):
        """Возвращает статистику очереди"""
        with self.lock:
            total_size = sum(f.get("file_size", 0) for f in self.file_queue)
            oldest = min([f["timestamp"] for f in self.file_queue]) if self.file_queue else None
            newest = max([f["timestamp"] for f in self.file_queue]) if self.file_queue else None
            
            return {
                "total_files": len(self.file_queue),
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "max_queue_size": self.max_queue_size,
                "max_file_age_hours": self.max_file_age_hours,
                "oldest_file": datetime.fromtimestamp(oldest).isoformat() if oldest else None,
                "newest_file": datetime.fromtimestamp(newest).isoformat() if newest else None,
                "files_by_type": self._count_by_type()
            }
    
    def _count_by_type(self):
        """Подсчитывает файлы по типам"""
        counts = {}
        for f in self.file_queue:
            ftype = f.get("file_type", "unknown")
            counts[ftype] = counts.get(ftype, 0) + 1
        return counts
    
    def force_cleanup_all(self):
        """Принудительно очищает все файлы"""
        with self.lock:
            removed_count = 0
            for file_info in self.file_queue:
                try:
                    if os.path.exists(file_info["file_path"]):
                        os.remove(file_info["file_path"])
                        removed_count += 1
                except Exception as e:
                    logger.error(f"Ошибка при force cleanup: {e}")
            
            self.file_queue = []
            self._save_queue()
            logger.info(f"Принудительная очистка: удалено {removed_count} файлов")
            return removed_count
    
    def get_all_files(self):
        """Возвращает копию очереди (для отладки)"""
        with self.lock:
            return self.file_queue.copy()


# Глобальный экземпляр менеджера очереди
_queue_manager = None

def init_queue_manager(upload_dir: str, max_queue_size: int = 100, max_file_age_hours: int = 1):
    """Инициализирует глобальный менеджер очереди"""
    global _queue_manager
    if _queue_manager is None:
        _queue_manager = FileQueueManager(upload_dir, max_queue_size, max_file_age_hours)
        logger.info(f"Менеджер очереди инициализирован: макс. {max_queue_size} файлов, время жизни {max_file_age_hours} ч")
    return _queue_manager

def get_queue_manager():
    """Возвращает глобальный менеджер очереди"""
    global _queue_manager
    if _queue_manager is None:
        raise RuntimeError("Queue manager not initialized. Call init_queue_manager first.")
    return _queue_manager