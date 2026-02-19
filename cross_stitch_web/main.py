import os
import shutil
import uuid
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw, ImageFont
import uvicorn
from contextlib import asynccontextmanager
import time
# Импорт справочника цветов DMC
from dmc_colors import find_closest_dmc_color, DMC_COLORS
# Импорт менеджера очереди
from file_queue import init_queue_manager, get_queue_manager

# Конфигурация
UPLOAD_DIR = "uploads"
MAX_FILE_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 10 * 1024 * 1024))  # 10MB по умолчанию

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    print(f"🚀 Application started. Upload directory: {UPLOAD_DIR}")
    
    # Получаем менеджер очереди
    qm = get_queue_manager()
    stats = qm.get_queue_stats()
    print(f"📊 Статистика очереди при запуске:")
    print(f"   - Файлов в очереди: {stats['total_files']}")
    print(f"   - Общий размер: {stats['total_size_mb']:.2f} MB")
    print(f"   - Макс. размер очереди: {stats['max_queue_size']}")
    print(f"   - Макс. возраст файлов: {stats['max_file_age_hours']} ч")
    
    yield
    
    # Shutdown
    print("👋 Application shutting down...")
    stats = qm.get_queue_stats()
    print(f"📊 Финальная статистика очереди:")
    print(f"   - Файлов в очереди: {stats['total_files']}")
    print(f"   - Общий размер: {stats['total_size_mb']:.2f} MB")

app = FastAPI(
    title="Cross Stitch Pattern Generator",
    lifespan=lifespan,
    docs_url="/docs" if os.getenv("ENVIRONMENT") != "production" else None,
    redoc_url="/redoc" if os.getenv("ENVIRONMENT") != "production" else None
)

# Создаем необходимые директории
os.makedirs("uploads", exist_ok=True)
os.makedirs("static", exist_ok=True)

# Инициализируем менеджер очереди
# Параметры: max_queue_size=100, max_file_age_hours=1
queue_manager = init_queue_manager(
    upload_dir="uploads",
    max_queue_size=int(os.getenv("MAX_QUEUE_SIZE", 100)),
    max_file_age_hours=int(os.getenv("MAX_FILE_AGE_HOURS", 1))
)

# Монтируем статические файлы
app.mount("/static", StaticFiles(directory="static"), name="static")

def simplify_palette(image, num_colors):
    """Упрощает палитру изображения до заданного количества цветов."""
    return image.quantize(colors=num_colors, method=Image.MEDIANCUT).convert('RGB')

def get_contrast_color(rgb):
    """Определяет контрастный цвет (черный или белый) для текста на фоне."""
    r, g, b = rgb
    brightness = (r * 299 + g * 587 + b * 114) / 1000
    return (0, 0, 0) if brightness > 128 else (255, 255, 255)

def create_numbered_pattern(
    image_path: str,
    output_image_path: str,
    max_width_cells: int = 80,
    max_colors: int = 24,
    cell_size: int = 40
):
    """
    Генерирует схему для вышивки с номерами цветов DMC в каждой ячейке.
    """
    
    # Открываем изображение
    original = Image.open(image_path)
    
    # Рассчитываем размер с сохранением пропорций
    aspect_ratio = original.height / original.width
    new_width = min(max_width_cells, original.width)
    new_height = int(new_width * aspect_ratio)
    
    print(f"Генерация схемы: {new_width} x {new_height} крестиков")
    
    # Изменяем размер и упрощаем цвета
    small_img = original.resize((new_width, new_height), Image.Resampling.LANCZOS)
    quantized = simplify_palette(small_img, max_colors)
    
    # Получаем уникальные цвета
    unique_colors = sorted(set(quantized.getdata()))
    
    # Создаем маппинг RGB -> DMC
    color_to_dmc = {}
    dmc_to_rgb = {}
    dmc_numbers = set()
    
    for rgb in unique_colors:
        dmc_num, dmc_name, dmc_rgb = find_closest_dmc_color(rgb)
        color_to_dmc[rgb] = {
            "number": dmc_num,
            "name": dmc_name,
            "original_rgb": rgb,
            "dmc_rgb": dmc_rgb
        }
        dmc_to_rgb[dmc_num] = dmc_rgb
        dmc_numbers.add(dmc_num)
    
    # Сортируем DMC номера для последовательной нумерации в схеме
    sorted_dmc_numbers = sorted(dmc_numbers)
    dmc_index_map = {dmc_num: i+1 for i, dmc_num in enumerate(sorted_dmc_numbers)}
    
    # Создаем обратный маппинг для отображения
    display_color_map = {}
    for rgb, info in color_to_dmc.items():
        display_color_map[rgb] = {
            "display_number": dmc_index_map[info["number"]],
            "dmc_number": info["number"],
            "dmc_name": info["name"],
            "dmc_rgb": info["dmc_rgb"]
        }
    
    # Создаем изображение для схемы
    img_width = new_width * cell_size
    img_height = new_height * cell_size
    
    pattern_img = Image.new('RGB', (img_width, img_height), 'white')
    draw = ImageDraw.Draw(pattern_img)
    
    # Загружаем шрифт
    try:
        font_size = cell_size // 2
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except:
            try:
                font = ImageFont.truetype("arialbd.ttf", font_size)
            except:
                font = ImageFont.load_default()
    except:
        font = ImageFont.load_default()
    
    # Рисуем сетку и заполняем цветом
    for y in range(new_height):
        for x in range(new_width):
            # Получаем оригинальный цвет пикселя
            original_rgb = quantized.getpixel((x, y))
            
            # Получаем соответствующий DMC цвет и номер для отображения
            display_info = display_color_map[original_rgb]
            dmc_rgb = display_info["dmc_rgb"]
            display_number = display_info["display_number"]
            
            # Координаты ячейки
            x1 = x * cell_size
            y1 = y * cell_size
            x2 = x1 + cell_size
            y2 = y1 + cell_size
            
            # Заливаем ячейку DMC цветом
            draw.rectangle([x1, y1, x2, y2], fill=dmc_rgb, outline=None)
            
            # Добавляем текстуру "крестика"
            texture_color = tuple(int(c * 0.95) for c in dmc_rgb)
            draw.line([(x1+2, y1+2), (x2-2, y2-2)], fill=texture_color, width=1)
            draw.line([(x1+2, y2-2), (x2-2, y1+2)], fill=texture_color, width=1)
            
            # Добавляем номер цвета
            text = str(display_number)
            
            # Получаем размер текста
            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            except:
                text_width = font_size // 2
                text_height = font_size // 2
            
            # Позиция для текста (по центру)
            text_x = x1 + (cell_size - text_width) // 2
            text_y = y1 + (cell_size - text_height) // 2
            
            # Определяем контрастный цвет для текста
            brightness = (dmc_rgb[0] * 299 + dmc_rgb[1] * 587 + dmc_rgb[2] * 114) / 1000
            text_color = (0, 0, 0) if brightness > 128 else (255, 255, 255)
            shadow_color = (255, 255, 255) if brightness > 128 else (0, 0, 0)
            
            # Тень и текст
            draw.text((text_x+1, text_y+1), text, fill=shadow_color, font=font)
            draw.text((text_x, text_y), text, fill=text_color, font=font)
    
    # Рисуем сетку
    grid_color = (100, 100, 100)
    for i in range(new_width + 1):
        x = i * cell_size
        draw.line([(x, 0), (x, img_height)], fill=grid_color, width=1)
    
    for i in range(new_height + 1):
        y = i * cell_size
        draw.line([(0, y), (img_width, y)], fill=grid_color, width=1)
    
    # Толстые линии каждые 10 клеток
    thick_color = (0, 0, 0)
    for i in range(0, new_width + 1, 10):
        x = i * cell_size
        draw.line([(x, 0), (x, img_height)], fill=thick_color, width=2)
    
    for i in range(0, new_height + 1, 10):
        y = i * cell_size
        draw.line([(0, y), (img_width, y)], fill=thick_color, width=2)
    
    # Добавляем поля для номеров строк/столбцов
    margin = 30
    full_img = Image.new('RGB', (img_width + 2*margin, img_height + 2*margin), 'white')
    full_img.paste(pattern_img, (margin, margin))
    draw = ImageDraw.Draw(full_img)
    
    # Номера строк
    for y in range(new_height):
        y_pos = margin + y * cell_size + cell_size // 2
        draw.text((5, y_pos - 7), str(y+1), fill=(0,0,0), font=font)
        draw.text((img_width + margin + 5, y_pos - 7), str(y+1), fill=(0,0,0), font=font)
    
    # Номера столбцов
    for x in range(new_width):
        x_pos = margin + x * cell_size + cell_size // 2
        draw.text((x_pos - 7, 5), str(x+1), fill=(0,0,0), font=font)
        draw.text((x_pos - 7, img_height + margin + 5), str(x+1), fill=(0,0,0), font=font)
    
    # Сохраняем результат
    full_img.save(output_image_path, 'PNG', quality=95)
    
    # Подготавливаем информацию о цветах для фронтенда
    color_info = {}
    for i, dmc_num in enumerate(sorted_dmc_numbers, 1):
        color_info[f"color_{i}"] = {
            "display_number": i,
            "dmc_number": dmc_num,
            "name": DMC_COLORS[dmc_num]["name"],
            "rgb": DMC_COLORS[dmc_num]["rgb"]
        }
    
    return {
        "width": new_width,
        "height": new_height,
        "colors": len(sorted_dmc_numbers),
        "color_map": color_info,
        "cell_size": cell_size
    }

@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.post("/generate")
async def generate_pattern(
    file: UploadFile = File(...),
    max_width: int = Form(80),
    max_colors: int = Form(24),
    cell_size: int = Form(40)
):
    """Генерирует схему из загруженного изображения."""
    
    # Валидация
    if not file.content_type.startswith('image/'):
        raise HTTPException(400, "Файл должен быть изображением")
    
    if max_width < 10 or max_width > 200:
        raise HTTPException(400, "Ширина должна быть от 10 до 200")
    
    if max_colors < 2 or max_colors > 50:
        raise HTTPException(400, "Количество цветов должно быть от 2 до 50")
    
    if cell_size < 20 or cell_size > 60:
        raise HTTPException(400, "Размер ячейки должен быть от 20 до 60")
    
    # Проверка размера файла
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(400, f"Файл слишком большой. Максимальный размер: {MAX_FILE_SIZE/1024/1024}MB")
    
    # Генерируем timestamp для имени файла
    timestamp = int(time.time() * 1000)  # миллисекунды для уникальности
    file_id = f"{timestamp}_{uuid.uuid4().hex[:8]}"
    
    # Сохраняем загруженный файл с timestamp
    input_ext = os.path.splitext(file.filename)[1]
    input_path = f"uploads/{file_id}_input{input_ext}"
    output_image = f"uploads/{file_id}_numbered_pattern.png"
    output_preview = f"uploads/{file_id}_preview.png"
    
    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Добавляем входной файл в очередь
    queue_manager.add_file(input_path, file_id, "input")
    
    try:
        # Генерируем схему с номерами
        result = create_numbered_pattern(
            input_path, 
            output_image,
            max_width_cells=max_width,
            max_colors=max_colors,
            cell_size=cell_size
        )
        
        # Создаем превью
        img = Image.open(output_image)
        img.thumbnail((400, 400))
        img.save(output_preview)
        
        # Добавляем сгенерированные файлы в очередь
        print(output_image +  file_id + "pattern")
        queue_manager.add_file(output_image, file_id, "pattern")
        queue_manager.add_file(output_preview, file_id, "preview")
        
        # Добавляем пути к файлам в результат
        result["image_url"] = f"/download/{os.path.basename(output_image)}"
        result["preview_url"] = f"/download/{os.path.basename(output_preview)}"
        result["file_id"] = file_id
        result["timestamp"] = timestamp
        
        return JSONResponse(result)
        
    except Exception as e:
        # В случае ошибки удаляем входной файл из очереди
        queue_manager.remove_by_file_id(file_id)
        raise HTTPException(500, f"Ошибка генерации: {str(e)}")

@app.get("/download/{filename}")
async def download_file(filename: str):
    """Скачивает сгенерированный файл."""
    file_path = f"uploads/{filename}"
    if not os.path.exists(file_path):
        raise HTTPException(404, "Файл не найден")
    return FileResponse(file_path, filename=filename)

@app.get("/admin/queue-stats")
async def get_queue_stats():
    """Возвращает статистику очереди файлов (только для администрирования)"""
    # В продакшене добавьте аутентификацию!
    qm = get_queue_manager()
    return JSONResponse(qm.get_queue_stats())

@app.post("/admin/cleanup-now")
async def force_cleanup():
    """Принудительно запускает очистку старых файлов"""
    qm = get_queue_manager()
    qm.cleanup_old_files()
    qm.enforce_queue_size()
    return {"message": "Cleanup completed", "stats": qm.get_queue_stats()}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)