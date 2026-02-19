#!/usr/bin/env python3
# fix_queue.py - Скрипт для исправления проблем с очередью

import os
import json
import shutil
from datetime import datetime

def fix_queue():
    """Исправляет проблемы с файлом очереди"""
    
    queue_file = 'uploads/.file_queue.json'
    backup_dir = 'uploads/backups'
    
    print("🔧 Исправление очереди файлов")
    print("=" * 50)
    
    # Создаем директорию для бэкапов
    os.makedirs(backup_dir, exist_ok=True)
    
    # Проверяем существование файла очереди
    if not os.path.exists(queue_file):
        print("❌ Файл очереди не найден")
        return
    
    # Проверяем размер файла
    file_size = os.path.getsize(queue_file)
    print(f"📄 Размер файла очереди: {file_size} байт")
    
    if file_size == 0:
        print("⚠️  Файл очереди пуст")
        # Создаем бэкап
        backup_name = f"{backup_dir}/empty_queue_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        shutil.copy2(queue_file, backup_name)
        print(f"✅ Бэкап создан: {backup_name}")
        
        # Создаем новый пустой файл очереди
        with open(queue_file, 'w') as f:
            json.dump([], f)
        print("✅ Создан новый файл очереди")
        return
    
    # Пытаемся прочитать файл
    try:
        with open(queue_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                raise ValueError("Пустой файл")
            
            data = json.loads(content)
            
            if not isinstance(data, list):
                raise ValueError(f"Ожидался список, получен {type(data)}")
            
            print(f"✅ Файл очереди корректен, содержит {len(data)} записей")
            
            # Проверяем существование файлов из очереди
            missing_files = []
            for item in data:
                file_path = item.get('file_path')
                if file_path and not os.path.exists(file_path):
                    missing_files.append(file_path)
            
            if missing_files:
                print(f"⚠️  Найдено {len(missing_files)} отсутствующих файлов в очереди")
                # Очищаем отсутствующие файлы из очереди
                data = [item for item in data if os.path.exists(item.get('file_path', ''))]
                
                # Сохраняем исправленную очередь
                backup_name = f"{backup_dir}/fixed_queue_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(backup_name, 'w') as f:
                    json.dump(data, f, indent=2)
                
                with open(queue_file, 'w') as f:
                    json.dump(data, f, indent=2)
                
                print(f"✅ Очередь исправлена, удалено {len(missing_files)} записей")
            
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка JSON: {e}")
        
        # Создаем бэкап поврежденного файла
        backup_name = f"{backup_dir}/corrupted_queue_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        shutil.copy2(queue_file, backup_name)
        print(f"✅ Бэкап поврежденного файла создан: {backup_name}")
        
        # Создаем новый пустой файл очереди
        with open(queue_file, 'w') as f:
            json.dump([], f)
        print("✅ Создан новый файл очереди")
        
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")

if __name__ == "__main__":
    fix_queue()