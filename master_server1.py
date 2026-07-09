import socket
import threading
import json
import os

class MasterServer:
    def __init__(self, host='0.0.0.0', port=9999):
        self.host = host
        self.port = port
        self.active_rooms = {}
        self.leaderboard_file = "leaderboard.json"
        self.lock = threading.Lock()
        self.init_leaderboard()

    def init_leaderboard(self):
        if not os.path.exists(self.leaderboard_file):
            default_data = [
                {"player": "Alpha_Zero", "rating": 1500},
                {"player": "Subspace_King", "rating": 1420},
                {"player": "Quantum_Pawn", "rating": 1200}
            ]
            with open(self.leaderboard_file, "w", encoding="utf-8") as f:
                json.dump(default_data, f, ensure_ascii=False, indent=4)

    def get_leaderboard(self):
        try:
            with open(self.leaderboard_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def update_rating(self, player_name, points):
        with self.lock:
            data = self.get_leaderboard()
            player_found = False
            for p in data:
                if p["player"] == player_name:
                    p["rating"] += points
                    player_found = True
                    break
            if not player_found:
                data.append({"player": player_name, "rating": 1000 + points})
            data.sort(key=lambda x: x["rating"], reverse=True)
            with open(self.leaderboard_file, "w", encoding="utf-8") as f:
                json.dump(data[:10], f, ensure_ascii=False, indent=4)

    def start(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen()
        print(f"[MASTER] Облачный мастер-сервер запущен на {self.host}:{self.port}")
        print("[MASTER] Ожидание запросов от игровых клиентов...")
        
        while True:
            try:
                conn, addr = server.accept()
                threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()
            except Exception as e:
                print(f"[MASTER CRITICAL ERROR] {e}")

    def handle_client(self, conn, addr):
        try:
            data = conn.recv(2048).decode('utf-8')
            if not data:
                return
            request = json.loads(data)
            action = request.get("action")
            
            if action == "register_room":
                room_name = request.get("room_name")
                game_port = request.get("port", 5555)
                with self.lock:
                    self.active_rooms[room_name] = (addr[0], game_port)
                print(f"[MASTER] Комната '{room_name}' зарегистрирована для {addr[0]}:{game_port}")
                conn.sendall(json.dumps({"status": "ok"}).encode('utf-8'))
                
            elif action == "get_rooms":
                with self.lock:
                    response = json.dumps({"status": "success", "rooms": self.active_rooms})
                conn.sendall(response.encode('utf-8'))
                
            elif action == "get_leaderboard":
                response = json.dumps({"status": "success", "leaderboard": self.get_leaderboard()})
                conn.sendall(response.encode('utf-8'))
                
            elif action == "match_over":
                winner = request.get("winner")
                self.update_rating(winner, 25)
                print(f"[MASTER] Рейтинг игрока '{winner}' увеличен на +25 очков.")
                conn.sendall(json.dumps({"status": "updated"}).encode('utf-8'))
                
        except Exception as e:
            print(f"[MASTER ERROR] Ошибка обработки запроса от {addr}: {e}")
        finally:
            conn.close()

if __name__ == "__main__":
    MasterServer().start()
