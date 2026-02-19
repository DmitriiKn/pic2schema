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

# Конфигурация
UPLOAD_DIR = "uploads"
MAX_FILE_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 10 * 1024 * 1024))  # 10MB по умолчанию

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    print(f"🚀 Application started. Upload directory: {UPLOAD_DIR}")
    yield
    # Shutdown
    print("👋 Application shutting down...")
    # Очистка старых файлов (старше 1 часа)
    current_time = time.time()
    for filename in os.listdir(UPLOAD_DIR):
        filepath = os.path.join(UPLOAD_DIR, filename)
        if os.path.isfile(filepath):
            if current_time - os.path.getmtime(filepath) > 3600:
                os.remove(filepath)
                print(f"Removed old file: {filename}")

app = FastAPI(
    title="Cross Stitch Pattern Generator",
    lifespan=lifespan,
    docs_url="/docs" if os.getenv("ENVIRONMENT") != "production" else None,
    redoc_url="/redoc" if os.getenv("ENVIRONMENT") != "production" else None
)

# Создаем необходимые директории
os.makedirs("uploads", exist_ok=True)
os.makedirs("static", exist_ok=True)

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
    cell_size: int = 40  # Увеличиваем размер ячейки для читаемости номеров
):
    """
    Генерирует схему для вышивки с номерами цветов в каждой ячейке.
    Возвращает PNG с цветными ячейками и номерами.
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
    color_map = {color: i+1 for i, color in enumerate(unique_colors)}
    reverse_color_map = {v: k for k, v in color_map.items()}
    
    # Создаем изображение для схемы
    img_width = new_width * cell_size
    img_height = new_height * cell_size
    
    pattern_img = Image.new('RGB', (img_width, img_height), 'white')
    draw = ImageDraw.Draw(pattern_img)
    
    # Пытаемся загрузить шрифт побольше для номеров
    try:
        # Пробуем разные шрифты
        font_size = cell_size // 2
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except:
            try:
                font = ImageFont.truetype("arialbd.ttf", font_size)
            except:
                try:
                    font = ImageFont.truetype("Arial Bold", font_size)
                except:
                    font = ImageFont.load_default()
    except:
        font = ImageFont.load_default()
    
    # Рисуем сетку и заполняем цветом
    for y in range(new_height):
        for x in range(new_width):
            # Получаем цвет для этой ячейки
            color = reverse_color_map[color_map[quantized.getpixel((x, y))]]
            color_number = color_map[quantized.getpixel((x, y))]
            
            # Координаты ячейки
            x1 = x * cell_size
            y1 = y * cell_size
            x2 = x1 + cell_size
            y2 = y1 + cell_size
            
            # Заливаем ячейку цветом
            draw.rectangle([x1, y1, x2, y2], fill=color, outline=None)
            
            # Добавляем текстуру "крестика" (опционально)
            # Рисуем два диагональных креста
            line_color = get_contrast_color(color)
            # Слегка затемняем/осветляем для текстуры
            texture_color = tuple(int(c * 0.95) for c in color)
            
            # Рисуем тонкие диагональные линии для имитации крестика
            draw.line([(x1+2, y1+2), (x2-2, y2-2)], fill=texture_color, width=1)
            draw.line([(x1+2, y2-2), (x2-2, y1+2)], fill=texture_color, width=1)
            
            # Добавляем номер цвета в центр ячейки
            text = str(color_number)
            
            # Получаем размер текста для центрирования
            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            except:
                text_width = font_size // 2
                text_height = font_size // 2
            
            # Позиция для текста (по центру ячейки)
            text_x = x1 + (cell_size - text_width) // 2
            text_y = y1 + (cell_size - text_height) // 2
            
            # Определяем контрастный цвет для текста
            text_color = get_contrast_color(color)
            
            # Рисуем текст с небольшой тенью для читаемости
            if text_color == (255, 255, 255):
                shadow_color = (0, 0, 0)
            else:
                shadow_color = (255, 255, 255)
            
            # Тень
            draw.text((text_x+1, text_y+1), text, fill=shadow_color, font=font)
            # Основной текст
            draw.text((text_x, text_y), text, fill=text_color, font=font)
    
    # Рисуем сетку (толстые линии)
    grid_color = (100, 100, 100)
    
    # Вертикальные линии
    for i in range(new_width + 1):
        x = i * cell_size
        draw.line([(x, 0), (x, img_height)], fill=grid_color, width=1)
    
    # Горизонтальные линии
    for i in range(new_height + 1):
        y = i * cell_size
        draw.line([(0, y), (img_width, y)], fill=grid_color, width=1)
    
    # Рисуем более толстые линии каждые 10 клеток для удобства
    thick_color = (0, 0, 0)
    for i in range(0, new_width + 1, 10):
        x = i * cell_size
        draw.line([(x, 0), (x, img_height)], fill=thick_color, width=2)
    
    for i in range(0, new_height + 1, 10):
        y = i * cell_size
        draw.line([(0, y), (img_width, y)], fill=thick_color, width=2)
    
    # Добавляем номера строк и столбцов по краям
    margin = 30
    full_img = Image.new('RGB', (img_width + 2*margin, img_height + 2*margin), 'white')
    full_img.paste(pattern_img, (margin, margin))
    draw = ImageDraw.Draw(full_img)
    
    # Номера строк (слева и справа)
    for y in range(new_height):
        y_pos = margin + y * cell_size + cell_size // 2
        # Слева
        draw.text((5, y_pos - 7), str(y+1), fill=(0,0,0), font=font)
        # Справа
        draw.text((img_width + margin + 5, y_pos - 7), str(y+1), fill=(0,0,0), font=font)
    
    # Номера столбцов (сверху и снизу)
    for x in range(new_width):
        x_pos = margin + x * cell_size + cell_size // 2
        # Сверху
        draw.text((x_pos - 7, 5), str(x+1), fill=(0,0,0), font=font)
        # Снизу
        draw.text((x_pos - 7, img_height + margin + 5), str(x+1), fill=(0,0,0), font=font)
    
    # Сохраняем результат
    full_img.save(output_image_path, 'PNG', quality=95)
    
    return {
        "width": new_width,
        "height": new_height,
        "colors": len(unique_colors),
        "color_map": {f"color_{k}": list(v) for k, v in reverse_color_map.items()},
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
    cell_size: int = Form(40)  # Добавляем размер ячейки
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
    
    # Сохраняем загруженный файл
    file_id = str(uuid.uuid4())
    input_path = f"uploads/{file_id}_input{os.path.splitext(file.filename)[1]}"
    output_image = f"uploads/{file_id}_numbered_pattern.png"
    output_preview = f"uploads/{file_id}_preview.png"
    
    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
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
        
        # Добавляем пути к файлам в результат
        result["image_url"] = f"/download/{file_id}_numbered_pattern.png"
        result["preview_url"] = f"/download/{file_id}_preview.png"
        result["file_id"] = file_id
        
        return JSONResponse(result)
        
    except Exception as e:
        raise HTTPException(500, f"Ошибка генерации: {str(e)}")
    
    finally:
        # Очищаем входной файл
        if os.path.exists(input_path):
            os.remove(input_path)

@app.get("/download/{filename}")
async def download_file(filename: str):
    """Скачивает сгенерированный файл."""
    file_path = f"uploads/{filename}"
    if not os.path.exists(file_path):
        raise HTTPException(404, "Файл не найден")
    return FileResponse(file_path, filename=filename)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)