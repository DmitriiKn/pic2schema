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
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}

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
            # Удаляем файлы старше 1 часа
            if current_time - os.path.getmtime(filepath) > 3600:
                os.remove(filepath)
                print(f"Removed old file: {filename}")

app = FastAPI(
    title="Cross Stitch Pattern Generator",
    lifespan=lifespan,
    # Отключаем документацию в production
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

def create_cross_stitch_pattern(
    image_path: str, 
    output_image_path: str, 
    output_text_path: str,
    max_width_cells: int = 80,
    max_colors: int = 24,
    cell_size: int = 20
):
    """Генерирует схему для вышивки крестиком."""
    
    # Открываем изображение
    original = Image.open(image_path)
    
    # Рассчитываем размер с сохранением пропорций
    aspect_ratio = original.height / original.width
    new_width = min(max_width_cells, original.width)
    new_height = int(new_width * aspect_ratio)
    
    # Изменяем размер и упрощаем цвета
    small_img = original.resize((new_width, new_height), Image.Resampling.LANCZOS)
    quantized = simplify_palette(small_img, max_colors)
    
    # Получаем уникальные цвета
    unique_colors = sorted(set(quantized.getdata()))
    color_map = {color: i+1 for i, color in enumerate(unique_colors)}
    reverse_color_map = {v: k for k, v in color_map.items()}
    
    # Сохраняем текстовую схему
    with open(output_text_path, 'w', encoding='utf-8') as f:
        f.write("СХЕМА ДЛЯ ВЫШИВКИ КРЕСТИКОМ\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Размер: {new_width} x {new_height} крестиков\n")
        f.write(f"Цветов: {len(unique_colors)}\n\n")
        
        f.write("ПАЛИТРА:\n")
        for color_id, rgb in reverse_color_map.items():
            f.write(f"  {color_id:2d} = RGB{tuple(rgb)}\n")
        f.write("\n")
        
        f.write("СХЕМА (цифры = номера цветов):\n")
        pixels = list(quantized.getdata())
        for y in range(new_height):
            row = pixels[y*new_width:(y+1)*new_width]
            row_str = ''.join([str(color_map.get(p, '0')) for p in row])
            # Группируем по 5 цифр для читаемости
            formatted = ' '.join([row_str[i:i+5] for i in range(0, len(row_str), 5)])
            f.write(f"{y+1:3d} | {formatted}\n")
    
    # Создаем PNG схему
    img_width = new_width * cell_size
    img_height = new_height * cell_size
    
    pattern_img = Image.new('RGB', (img_width, img_height), 'white')
    
    # Заполняем цветом
    for y in range(new_height):
        for x in range(new_width):
            color = reverse_color_map[color_map[quantized.getpixel((x, y))]]
            
            for i in range(cell_size):
                for j in range(cell_size):
                    # Эффект вышивки
                    if i < 2 or j < 2 or i > cell_size-3 or j > cell_size-3:
                        darker = tuple(int(c * 0.8) for c in color)
                        pattern_img.putpixel((x*cell_size + i, y*cell_size + j), darker)
                    elif (i + j) % 3 == 0:
                        darker = tuple(int(c * 0.9) for c in color)
                        pattern_img.putpixel((x*cell_size + i, y*cell_size + j), darker)
                    else:
                        pattern_img.putpixel((x*cell_size + i, y*cell_size + j), color)
    
    # Рисуем сетку
    grid_color = (200, 200, 200)
    draw = ImageDraw.Draw(pattern_img)
    
    for i in range(new_width + 1):
        x = i * cell_size
        draw.line([(x, 0), (x, img_height)], fill=grid_color, width=1)
    
    for i in range(new_height + 1):
        y = i * cell_size
        draw.line([(0, y), (img_width, y)], fill=grid_color, width=1)
    
    # Добавляем номера
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size=10)
    except:
        try:
            font = ImageFont.truetype("arial.ttf", size=10)
        except:
            font = ImageFont.load_default()
    
    for y in range(new_height):
        draw.text((2, y*cell_size + 2), str(y+1), fill=(0,0,0), font=font)
    
    for x in range(0, new_width, 5):
        draw.text((x*cell_size + 2, 2), str(x+1), fill=(0,0,0), font=font)
    
    pattern_img.save(output_image_path, 'PNG')
    
    return {
        "width": new_width,
        "height": new_height,
        "colors": len(unique_colors),
        "color_map": {f"color_{k}": list(v) for k, v in reverse_color_map.items()}
    }

@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.post("/generate")
async def generate_pattern(
    file: UploadFile = File(...),
    max_width: int = Form(80),
    max_colors: int = Form(24)
):
    """Генерирует схему из загруженного изображения."""
    
    # Валидация
    if not file.content_type.startswith('image/'):
        raise HTTPException(400, "Файл должен быть изображением")
    
    if max_width < 10 or max_width > 200:
        raise HTTPException(400, "Ширина должна быть от 10 до 200")
    
    if max_colors < 2 or max_colors > 50:
        raise HTTPException(400, "Количество цветов должно быть от 2 до 50")
    
    # Проверка размера файла
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(400, f"Файл слишком большой. Максимальный размер: {MAX_FILE_SIZE/1024/1024}MB")
    
    # Сохраняем загруженный файл
    file_id = str(uuid.uuid4())
    input_path = f"uploads/{file_id}_input{os.path.splitext(file.filename)[1]}"
    output_image = f"uploads/{file_id}_pattern.png"
    output_text = f"uploads/{file_id}_pattern.txt"
    
    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    try:
        # Генерируем схему
        result = create_cross_stitch_pattern(
            input_path, 
            output_image, 
            output_text,
            max_width_cells=max_width,
            max_colors=max_colors
        )
        
        # Добавляем пути к файлам в результат
        result["image_url"] = f"/download/{file_id}_pattern.png"
        result["text_url"] = f"/download/{file_id}_pattern.txt"
        result["preview_url"] = f"/preview/{file_id}"
        
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

@app.get("/preview/{file_id}")
async def get_preview(file_id: str):
    """Возвращает информацию для предпросмотра."""
    pattern_path = f"uploads/{file_id}_pattern.png"
    if not os.path.exists(pattern_path):
        raise HTTPException(404, "Схема не найдена")
    
    # Создаем уменьшенную версию для предпросмотра
    img = Image.open(pattern_path)
    img.thumbnail((400, 400))
    
    preview_path = f"uploads/{file_id}_preview.png"
    img.save(preview_path)
    
    return FileResponse(preview_path)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)