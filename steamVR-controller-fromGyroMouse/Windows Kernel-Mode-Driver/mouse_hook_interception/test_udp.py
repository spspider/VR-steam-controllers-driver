#!/usr/bin/env python3
"""
UDP Mouse Data Receiver
Тест для приёма данных от mouse_hook.exe
"""

import socket
import sys
import time
from collections import deque

# Настройки
UDP_IP = "127.0.0.1"
UDP_PORT = 5556
BUFFER_SIZE = 1024

# Статистика
stats = {
    'packets': 0,
    'errors': 0,
    'last_print': time.time()
}

# Буфер для визуализации движения
movement_buffer = deque(maxlen=50)

def parse_packet(data):
    """
    Парсинг UDP пакета
    Формат: MOUSE:deltaX,deltaY,buttons,timestamp
    """
    try:
        if not data.startswith('MOUSE:'):
            return None
        
        parts = data[6:].split(',')
        if len(parts) != 4:
            return None
        
        return {
            'deltaX': int(parts[0]),
            'deltaY': int(parts[1]),
            'buttons': int(parts[2]),
            'timestamp': int(parts[3])
        }
    except (ValueError, IndexError):
        return None

def visualize_movement(deltaX, deltaY):
    """Простая визуализация направления движения"""
    if deltaX == 0 and deltaY == 0:
        return "●"
    
    # Нормализация для визуализации
    magnitude = (deltaX**2 + deltaY**2) ** 0.5
    
    if magnitude > 10:
        arrow = "⬆"  # Сильное движение
        if abs(deltaX) > abs(deltaY):
            arrow = "➡" if deltaX > 0 else "⬅"
        else:
            arrow = "⬆" if deltaY < 0 else "⬇"
    else:
        arrow = "·"  # Слабое движение
    
    return arrow

def print_stats():
    """Вывод статистики"""
    print(f"\n{'='*60}")
    print(f"Packets received: {stats['packets']}")
    print(f"Parse errors: {stats['errors']}")
    print(f"Average rate: {stats['packets'] / (time.time() - start_time):.1f} packets/sec")
    
    if movement_buffer:
        print(f"\nRecent movement pattern:")
        pattern = ''.join(movement_buffer)
        print(f"[{pattern}]")
    
    print(f"{'='*60}\n")

def main():
    global start_time
    start_time = time.time()
    
    print("="*60)
    print("UDP Mouse Data Receiver")
    print("="*60)
    print(f"Listening on {UDP_IP}:{UDP_PORT}")
    print("Waiting for data from mouse_hook.exe...")
    print("Press Ctrl+C to exit\n")
    
    # Создать UDP сокет
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    
    try:
        while True:
            # Получить данные
            data, addr = sock.recvfrom(BUFFER_SIZE)
            packet = data.decode('utf-8', errors='ignore')
            
            # Парсинг
            parsed = parse_packet(packet)
            
            if parsed:
                stats['packets'] += 1
                
                # Визуализация
                arrow = visualize_movement(parsed['deltaX'], parsed['deltaY'])
                movement_buffer.append(arrow)
                
                # Вывод данных
                button_str = ""
                if parsed['buttons'] == 1:
                    button_str = "[LEFT]"
                elif parsed['buttons'] == 2:
                    button_str = "[RIGHT]"
                
                print(f"{arrow} X={parsed['deltaX']:4d} Y={parsed['deltaY']:4d} {button_str:8s} "
                      f"Time={parsed['timestamp']} Packets={stats['packets']}")
                
                # Статистика каждые 5 секунд
                if time.time() - stats['last_print'] > 5:
                    print_stats()
                    stats['last_print'] = time.time()
                    
            else:
                stats['errors'] += 1
                print(f"[ERROR] Invalid packet: {packet}")
    
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        print_stats()
        sock.close()
        sys.exit(0)

if __name__ == "__main__":
    main()