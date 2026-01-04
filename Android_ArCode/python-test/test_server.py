import socket
import time
import signal
import sys

class UDPServer:
    def __init__(self, host='0.0.0.0', port=4242):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(1.0)  # Таймаут для recvfrom
        self.sock.bind((host, port))
        self.running = True
        print(f"UDP Server listening on {host}:{port}")
        
        # Обработчик сигнала для Ctrl+C
        signal.signal(signal.SIGINT, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        print("\n\nReceived Ctrl+C, shutting down...")
        self.running = False
        
    def start(self):
        packet_count = 0
        last_print = time.time()
        
        try:
            while self.running:
                try:
                    data, addr = self.sock.recvfrom(1024)
                    packet_count += 1
                    
                    try:
                        message = data.decode('utf-8')
                        current_time = time.time()
                        
                        # Печатаем каждые 0.5 секунды
                        if current_time - last_print > 0.5:
                            print(f"\n[Packet #{packet_count}] From {addr}: {message}")
                            last_print = current_time
                        else:
                            print(".", end="", flush=True)
                            
                    except Exception as e:
                        print(f"\nError decoding packet: {e}")
                        
                except socket.timeout:
                    continue  # Продолжаем цикл при таймауте
                    
        except Exception as e:
            print(f"\nServer error: {e}")
        finally:
            print("\nClosing server...")
            self.sock.close()
    
    def stop(self):
        self.running = False

if __name__ == "__main__":
    server = UDPServer()
    server.start()