#!/usr/bin/env python3
"""
ArUco Marker Generator
Генерация маркеров для VR контроллеров и HMD
"""

import cv2
import cv2.aruco as aruco
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import os

def generate_marker_with_label(marker_id: int, marker_size: int, label: str, output_path: str):
    """
    Генерация ArUco маркера с подписью
    
    Args:
        marker_id: ID маркера (0=left, 1=right, 2=HMD)
        marker_size: Размер маркера в пикселях
        label: Текст подписи
        output_path: Путь для сохранения
    """
    # Генерация маркера
    dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    marker_image = aruco.generateImageMarker(dictionary, marker_id, marker_size)
    
    # Создать изображение с рамкой и подписью
    border_size = 50
    total_height = marker_size + border_size * 3  # Верх, низ, место для текста
    total_width = marker_size + border_size * 2
    
    # Белый фон
    final_image = np.ones((total_height, total_width), dtype=np.uint8) * 255
    
    # Вставить маркер
    y_offset = border_size
    x_offset = border_size
    final_image[y_offset:y_offset+marker_size, x_offset:x_offset+marker_size] = marker_image
    
    # Добавить текст с помощью PIL (для лучшего качества текста)
    pil_image = Image.fromarray(final_image)
    draw = ImageDraw.Draw(pil_image)
    
    # Попробовать загрузить шрифт (если доступен)
    try:
        font = ImageFont.truetype("arial.ttf", 30)
    except:
        font = ImageFont.load_default()
    
    # Текст сверху
    text_top = f"ID {marker_id}: {label}"
    bbox = draw.textbbox((0, 0), text_top, font=font)
    text_width = bbox[2] - bbox[0]
    text_x = (total_width - text_width) // 2
    draw.text((text_x, 10), text_top, fill=0, font=font)
    
    # Инструкции снизу
    text_bottom = f"Print at {marker_size//10}cm size"
    bbox = draw.textbbox((0, 0), text_bottom, font=font)
    text_width = bbox[2] - bbox[0]
    text_x = (total_width - text_width) // 2
    draw.text((text_x, marker_size + border_size + 10), text_bottom, fill=0, font=font)
    
    # Сохранить
    pil_image.save(output_path)
    print(f"✓ Generated marker ID {marker_id} ({label}): {output_path}")


def generate_multi_marker_sheet(output_path: str = "aruco_markers_sheet.png"):
    """
    Генерация листа с несколькими маркерами для печати
    """
    # Размеры в пикселях (для печати на A4)
    dpi = 300
    a4_width_inch = 8.27
    a4_height_inch = 11.69
    
    width_px = int(a4_width_inch * dpi)
    height_px = int(a4_height_inch * dpi)
    
    # Белый фон
    sheet = np.ones((height_px, width_px), dtype=np.uint8) * 255
    
    # Параметры маркеров
    marker_size = 600  # 2 дюйма при 300 DPI
    spacing = 100
    
    dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    
    markers_info = [
        (0, "LEFT CONTROLLER"),
        (1, "RIGHT CONTROLLER"),
        (2, "HMD (HEAD)")
    ]
    
    # Разместить маркеры
    y_pos = 300
    
    for marker_id, label in markers_info:
        # Генерация маркера
        marker_image = aruco.generateImageMarker(dictionary, marker_id, marker_size)
        
        # Центрирование
        x_pos = (width_px - marker_size) // 2
        
        # Вставить маркер
        sheet[y_pos:y_pos+marker_size, x_pos:x_pos+marker_size] = marker_image
        
        # Добавить подпись с помощью PIL
        pil_sheet = Image.fromarray(sheet)
        draw = ImageDraw.Draw(pil_sheet)
        
        try:
            font_title = ImageFont.truetype("arial.ttf", 50)
            font_id = ImageFont.truetype("arial.ttf", 40)
        except:
            font_title = ImageFont.load_default()
            font_id = ImageFont.load_default()
        
        # ID сверху
        id_text = f"ID {marker_id}"
        bbox = draw.textbbox((0, 0), id_text, font=font_id)
        text_width = bbox[2] - bbox[0]
        text_x = (width_px - text_width) // 2
        draw.text((text_x, y_pos - 80), id_text, fill=0, font=font_id)
        
        # Название снизу
        bbox = draw.textbbox((0, 0), label, font=font_title)
        text_width = bbox[2] - bbox[0]
        text_x = (width_px - text_width) // 2
        draw.text((text_x, y_pos + marker_size + 20), label, fill=0, font=font_title)
        
        sheet = np.array(pil_sheet)
        
        y_pos += marker_size + spacing + 150
    
    # Сохранить
    Image.fromarray(sheet).save(output_path, dpi=(dpi, dpi))
    print(f"✓ Generated multi-marker sheet: {output_path}")
    print(f"  Print this on A4 paper at actual size (100% scale)")


def generate_calibration_board(output_path: str = "aruco_calibration_board.png"):
    """
    Генерация калибровочной доски для калибровки камеры
    """
    dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    
    # Создать доску 5x7 маркеров
    board = aruco.GridBoard(
        (5, 7),           # 5 столбцов, 7 строк
        0.04,             # Размер маркера 4 см
        0.01,             # Расстояние между маркерами 1 см
        dictionary
    )
    
    # Генерация изображения доски
    img_size = 2000
    board_image = board.generateImage((img_size, int(img_size * 1.4)))
    
    # Добавить рамку и инструкции
    border = 100
    final_height = board_image.shape[0] + border * 2 + 200
    final_width = board_image.shape[1] + border * 2
    
    final_image = np.ones((final_height, final_width), dtype=np.uint8) * 255
    final_image[border:border+board_image.shape[0], 
                border:border+board_image.shape[1]] = board_image
    
    # Добавить текст
    pil_image = Image.fromarray(final_image)
    draw = ImageDraw.Draw(pil_image)
    
    try:
        font = ImageFont.truetype("arial.ttf", 40)
    except:
        font = ImageFont.load_default()
    
    title = "ArUco Calibration Board - Print on flat surface"
    bbox = draw.textbbox((0, 0), title, font=font)
    text_width = bbox[2] - bbox[0]
    text_x = (final_width - text_width) // 2
    draw.text((text_x, 30), title, fill=0, font=font)
    
    instructions = "Use this board to calibrate your camera for better tracking accuracy"
    bbox = draw.textbbox((0, 0), instructions, font=font)
    text_width = bbox[2] - bbox[0]
    text_x = (final_width - text_width) // 2
    draw.text((text_x, final_height - 150), instructions, fill=0, font=font)
    
    pil_image.save(output_path, dpi=(300, 300))
    print(f"✓ Generated calibration board: {output_path}")


def generate_all_markers():
    """Генерация всех необходимых маркеров"""
    print("=" * 60)
    print("ArUco Marker Generator for VR Tracking")
    print("=" * 60)
    print()
    
    # Создать папку для маркеров
    output_dir = "aruco_markers"
    os.makedirs(output_dir, exist_ok=True)
    
    # Размеры для печати
    marker_sizes = {
        'small': 200,   # ~5 см
        'medium': 400,  # ~10 см
        'large': 600,   # ~15 см
    }
    
    markers = [
        (0, "LEFT Controller"),
        (1, "RIGHT Controller"),
        (2, "HMD (Head)"),
    ]
    
    print("Generating individual markers...")
    print()
    
    for size_name, size_px in marker_sizes.items():
        print(f"Size: {size_name} ({size_px}px)")
        for marker_id, label in markers:
            filename = f"{output_dir}/marker_id{marker_id}_{size_name}_{label.lower().replace(' ', '_')}.png"
            generate_marker_with_label(marker_id, size_px, label, filename)
        print()
    
    print("Generating combined sheet...")
    generate_multi_marker_sheet(f"{output_dir}/all_markers_sheet.png")
    print()
    
    print("Generating calibration board...")
    generate_calibration_board(f"{output_dir}/calibration_board.png")
    print()
    
    print("=" * 60)
    print("All markers generated successfully!")
    print("=" * 60)
    print()
    print("PRINTING INSTRUCTIONS:")
    print("1. Print markers at ACTUAL SIZE (100% scale, no fit to page)")
    print("2. Use high-quality printer (300+ DPI recommended)")
    print("3. Print on thick matte paper (avoid glossy)")
    print("4. Mount on rigid surface (cardboard, foam board)")
    print("5. Keep markers flat and avoid creases")
    print()
    print("RECOMMENDED SIZES:")
    print("  - Controllers: 10-15 cm (medium/large)")
    print("  - HMD: 15-20 cm (large)")
    print("  - Larger markers = better detection at distance")
    print()
    print("MOUNTING:")
    print("  - LEFT Controller: Attach to left phone/device")
    print("  - RIGHT Controller: Attach to right phone/device")
    print("  - HMD: Attach to top or side of headset")
    print("  - Ensure markers are always visible to camera")
    print()


if __name__ == "__main__":
    # Проверка установки OpenCV
    try:
        import cv2
        print(f"OpenCV version: {cv2.__version__}")
    except ImportError:
        print("ERROR: OpenCV not installed!")
        print("Install with: pip install opencv-python opencv-contrib-python")
        exit(1)
    
    # Генерация маркеров
    generate_all_markers()
    
    print("Done! Check the 'aruco_markers' folder for all generated images.")