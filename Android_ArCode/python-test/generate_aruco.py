import cv2
import numpy as np

# Создаем детектор ArUco
dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)

# Генерация маркеров
for marker_id in range(10):
    # Создаем маркер 300x300 пикселей
    marker_image = np.zeros((300, 300), dtype=np.uint8)
    marker_image = cv2.aruco.generateImageMarker(dictionary, marker_id, 300, marker_image, 1)
    
    # Добавляем белую рамку
    marker_with_border = cv2.copyMakeBorder(marker_image, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    
    # Сохраняем
    cv2.imwrite(f"aruco_marker_{marker_id}.png", marker_with_border)
    print(f"Generated marker ID: {marker_id}")

print("Markers saved as PNG files")