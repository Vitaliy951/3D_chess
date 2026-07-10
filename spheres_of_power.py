# ==========================================
# ФАЙЛ: spheres_of_power.py
# ТРЁХМЕРНЫЕ ШАХМАТЫ «СФЕРЫ ВЛАСТИ»
# Исправленная версия для GitHub Actions
# ==========================================

import sys
import os
import json
import socket
import threading
import copy
import random
import time
import unittest

# Явно импортируем класс Ursina, чтобы избежать конфликта с функцией
from ursina import Ursina as UrsinaClass
from ursina import *
from ursina.prefabs.input_field import InputField

# --- Попытка импорта кастомного шейдера ---
try:
    from alpha_cube_shader import cube_transparency_shader
except ImportError:
    cube_transparency_shader = None
    print("[WARN] alpha_cube_shader.py не найден. Прозрачность отключена.")


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


MASTER_SERVER_IP = "127.0.0.1"  # замените на реальный IP вашего облачного сервера
MASTER_SERVER_PORT = 9999


def register_room_on_master(room_name, game_port=5555):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect((MASTER_SERVER_IP, MASTER_SERVER_PORT))
        payload = {"action": "register_room", "room_name": room_name, "port": game_port}
        s.sendall(json.dumps(payload).encode('utf-8'))
        s.close()
    except Exception as e:
        print(f"[NET ERROR] {e}")


def fetch_rooms_from_master():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect((MASTER_SERVER_IP, MASTER_SERVER_PORT))
        payload = {"action": "get_rooms"}
        s.sendall(json.dumps(payload).encode('utf-8'))
        response = s.recv(4096).decode('utf-8')
        s.close()
        data = json.loads(response)
        return data.get("rooms", {})
    except Exception as e:
        print(f"[NET ERROR] {e}")
        return {}


# ==========================================
# ЛОГИЧЕСКОЕ ЯДРО
# ==========================================

class Piece:
    def __init__(self, name, color, x, y, z):
        self.name = name
        self.color = color
        self.x = x
        self.y = y
        self.z = z

    def is_valid_move(self, target_x, target_y, target_z, board):
        if (target_x, target_y, target_z) == (self.x, self.y, self.z):
            return False
        if not (0 <= target_x < 8 and 0 <= target_y < 8 and 0 <= target_z < 8):
            return False

        target_piece = board.get_piece_at(target_x, target_y, target_z)
        if target_piece and target_piece.color == self.color:
            return False

        dx = abs(target_x - self.x)
        dy = abs(target_y - self.y)
        dz = abs(target_z - self.z)

        # ---- Логика фигур ----
        if self.name == 'R':  # Ладья – строго по одной оси
            diffs = [dx != 0, dy != 0, dz != 0]
            if sum(diffs) != 1:
                return False
            return True

        if self.name == 'N':  # Конь – вектор (2,1,0)
            dims = sorted([dx, dy, dz])
            return dims == [0, 1, 2]

        # Остальные фигуры (для прототипа) – ход на 1 клетку в любом направлении
        if max(dx, dy, dz) <= 1:
            return True
        return False


class Board:
    def __init__(self):
        self.pieces = []
        self.setup_pieces()

    def setup_pieces(self):
        self.pieces.clear()
        back_row = ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R']
        # Белые (слои 0 и 1)
        for x, name in enumerate(back_row):
            self.pieces.append(Piece(name, 'white', x, 0, 0))
        for x in range(8):
            self.pieces.append(Piece('P', 'white', x, 1, 0))
            self.pieces.append(Piece('P', 'white', x, 1, 1))
        self.pieces.append(Piece('R', 'white', 3, 0, 1))
        self.pieces.append(Piece('R', 'white', 4, 0, 1))
        # Чёрные (слои 6 и 7)
        for x, name in enumerate(back_row):
            self.pieces.append(Piece(name, 'black', x, 7, 7))
        for x in range(8):
            self.pieces.append(Piece('P', 'black', x, 6, 7))
            self.pieces.append(Piece('P', 'black', x, 6, 6))
        self.pieces.append(Piece('R', 'black', 3, 7, 6))
        self.pieces.append(Piece('R', 'black', 4, 7, 6))

    def get_piece_at(self, x, y, z):
        for p in self.pieces:
            if p.x == x and p.y == y and p.z == z:
                return p
        return None

    def move_piece(self, piece, tx, ty, tz):
        target = self.get_piece_at(tx, ty, tz)
        if target and target.color != piece.color:
            self.pieces.remove(target)
        piece.x, piece.y, piece.z = tx, ty, tz


# ==========================================
# СЕТЕВОЙ МЕНЕДЖЕР
# ==========================================

class NetworkManager:
    def __init__(self, game_instance):
        self.game = game_instance
        self.sock = None
        self.conn = None
        self.is_host = False
        self.my_color = 'white'
        self.saved_ip = None
        self.saved_port = 5555
        self.reconnecting = False
        self.reconnect_ui = None

    def start_as_host(self, port=5555):
        self.is_host = True
        self.my_color = 'white'
        self.saved_port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('0.0.0.0', port))
        self.sock.listen(1)
        print(f"[NET] Сервер на порту {port}")
        threading.Thread(target=self._accept_connection, daemon=True).start()

    def connect_to_host(self, ip, port=5555):
        self.is_host = False
        self.my_color = 'black'
        self.saved_ip = ip
        self.saved_port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.connect((ip, port))
            self.conn = self.sock
            print(f"[NET] Подключено к {ip}:{port}")
            threading.Thread(target=self._listen_network, daemon=True).start()
        except Exception as e:
            print(f"[NET] Ошибка подключения: {e}")
            self.conn = None

    def _accept_connection(self):
        try:
            self.conn, addr = self.sock.accept()
            print(f"[NET] Подключён игрок из {addr}")
            self._listen_network()
        except Exception as e:
            print(f"[NET] Ошибка приёма: {e}")

    def send_move(self, fx, fy, fz, tx, ty, tz):
        if self.conn:
            try:
                move_str = f"{fx},{fy},{fz}:{tx},{ty},{tz}"
                self.conn.sendall(move_str.encode('utf-8'))
            except Exception as e:
                print(f"[NET] Ошибка отправки: {e}")

    def send_chat_message(self, nickname, message):
        if self.conn:
            try:
                packet = f"CHAT:[{nickname}]: {message}"
                self.conn.sendall(packet.encode('utf-8'))
            except Exception as e:
                print(f"[NET] Ошибка чата: {e}")

    def _listen_network(self):
        while True:
            try:
                data = self.conn.recv(1024)
                if not data:
                    raise socket.error("Соединение потеряно")
                msg = data.decode('utf-8')
                if msg.startswith("CHAT:"):
                    chat_content = msg.replace("CHAT:", "")
                    invoke(self.game.chat_ui.add_message, chat_content)
                else:
                    from_part, to_part = msg.split(':')
                    fx, fy, fz = map(int, from_part.split(','))
                    tx, ty, tz = map(int, to_part.split(','))
                    invoke(self.game.execute_network_move, fx, fy, fz, tx, ty, tz)
            except (socket.error, ConnectionResetError):
                print("[NET] Связь оборвана!")
                invoke(self.start_reconnect_flow)
                break

    def start_reconnect_flow(self):
        if self.reconnecting:
            return
        self.reconnecting = True
        self.game.game_active = False
        self.reconnect_ui = Text(
            text="СВЯЗЬ ПОТЕРЯНА.\nПопытка ресинхронизации...",
            position=(0, 0), origin=(0, 0), scale=2, color=color.red
        )
        threading.Thread(target=self._attempt_reconnect_loop, daemon=True).start()

    def _attempt_reconnect_loop(self):
        attempts = 0
        max_attempts = 10
        while attempts < max_attempts and self.reconnecting:
            time.sleep(3.0)
            attempts += 1
            print(f"[NET] Попытка {attempts}/{max_attempts}...")
            try:
                new_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                new_sock.settimeout(2.0)
                if self.is_host:
                    new_sock.bind(('0.0.0.0', self.saved_port))
                    new_sock.listen(1)
                    self.conn, addr = new_sock.accept()
                else:
                    new_sock.connect((self.saved_ip, self.saved_port))
                    self.conn = new_sock
                print("[NET] Восстановлено!")
                invoke(self.successfully_reconnected)
                return
            except Exception:
                continue
        invoke(self.abort_game_due_to_disconnect)

    def successfully_reconnected(self):
        self.reconnecting = False
        self.game.game_active = True
        if self.reconnect_ui:
            destroy(self.reconnect_ui)
        threading.Thread(target=self._listen_network, daemon=True).start()

    def abort_game_due_to_disconnect(self):
        self.reconnecting = False
        if self.reconnect_ui:
            self.reconnect_ui.text = "НЕ УДАЛОСЬ ПОДКЛЮЧИТЬСЯ.\nСессия аннулирована."


# ==========================================
# ИИ (МИНИМАКС)
# ==========================================

class ChessAI:
    def __init__(self, color='black'):
        self.ai_color = color
        self.player_color = 'white' if color == 'black' else 'black'
        self.piece_values = {'P': 10, 'N': 30, 'B': 35, 'R': 50, 'Q': 90, 'K': 10000}

    def evaluate_board(self, board):
        score = 0
        for p in board.pieces:
            val = self.piece_values.get(p.name, 0)
            if 2 <= p.x <= 5 and 2 <= p.y <= 5:
                val += 1
            if p.z in (3, 4):
                val += 2
            score += val if p.color == self.ai_color else -val
        return score

    def get_all_legal_moves(self, board, color):
        moves = []
        for p in board.pieces:
            if p.color != color:
                continue
            for tx in range(8):
                for ty in range(8):
                    for tz in range(8):
                        if p.is_valid_move(tx, ty, tz, board):
                            moves.append((p, tx, ty, tz))
        return moves

    def minimax(self, board, depth, alpha, beta, is_maximizing):
        if depth == 0 or len(board.pieces) < 2:
            return self.evaluate_board(board), None

        color = self.ai_color if is_maximizing else self.player_color
        legal_moves = self.get_all_legal_moves(board, color)
        if not legal_moves:
            return self.evaluate_board(board), None

        legal_moves.sort(key=lambda m: board.get_piece_at(m[1], m[2], m[3]) is not None, reverse=True)
        best_move = None

        if is_maximizing:
            max_eval = -float('inf')
            for move in legal_moves:
                piece, tx, ty, tz = move
                temp_board = copy.deepcopy(board)
                sim_piece = temp_board.get_piece_at(piece.x, piece.y, piece.z)
                temp_board.move_piece(sim_piece, tx, ty, tz)
                eval_score, _ = self.minimax(temp_board, depth-1, alpha, beta, False)
                if eval_score > max_eval:
                    max_eval = eval_score
                    best_move = (piece.x, piece.y, piece.z, tx, ty, tz)
                alpha = max(alpha, eval_score)
                if beta <= alpha:
                    break
            return max_eval, best_move
        else:
            min_eval = float('inf')
            for move in legal_moves:
                piece, tx, ty, tz = move
                temp_board = copy.deepcopy(board)
                sim_piece = temp_board.get_piece_at(piece.x, piece.y, piece.z)
                temp_board.move_piece(sim_piece, tx, ty, tz)
                eval_score, _ = self.minimax(temp_board, depth-1, alpha, beta, True)
                if eval_score < min_eval:
                    min_eval = eval_score
                    best_move = (piece.x, piece.y, piece.z, tx, ty, tz)
                beta = min(beta, eval_score)
                if beta <= alpha:
                    break
            return min_eval, best_move

    def make_move(self, board):
        _, best_move = self.minimax(board, depth=2, alpha=-float('inf'), beta=float('inf'), is_maximizing=True)
        if best_move:
            fx, fy, fz, tx, ty, tz = best_move
            piece = board.get_piece_at(fx, fy, fz)
            return piece, tx, ty, tz
        return None, None, None, None


# ==========================================
# ЧАТ UI
# ==========================================

class ChatUI(Entity):
    def __init__(self, game_instance):
        super().__init__(parent=camera.ui)
        self.game = game_instance
        self.messages = []
        self.chat_box = Text(text="", position=(-0.85, -0.1), scale=1.1, color=color.light_gray)
        self.input_field = InputField(
            max_lines=1,
            position=(-0.65, -0.4),
            scale=(0.4, 0.04),
            enabled=False,
            placeholder="Нажмите Enter для чата..."
        )

    def toggle_chat(self):
        if not self.input_field.enabled:
            self.input_field.enable()
            self.input_field.active = True
        else:
            if self.input_field.text.strip():
                my_nick = "Белый" if self.game.network.my_color == 'white' else "Чёрный"
                self.add_message(f"[{my_nick}]: {self.input_field.text}")
                self.game.network.send_chat_message(my_nick, self.input_field.text)
            self.input_field.text = ""
            self.input_field.disable()

    def add_message(self, text):
        self.messages.append(text)
        if len(self.messages) > 6:
            self.messages.pop(0)
        self.chat_box.text = "\n".join(self.messages)


# ==========================================
# ГЛАВНОЕ МЕНЮ
# ==========================================

class MainMenu(Entity):
    def __init__(self, game_instance):
        super().__init__(parent=camera.ui)
        self.game = game_instance
        self.faction_color = color.cyan
        self.laser_color = color.yellow

        self.bg = Entity(parent=self, model='quad', scale=(2, 1), color=color.rgba(10, 20, 30, 235), z=1)
        self.title = Text(text="SPHERES OF POWER", scale=4, origin=(0, 0), y=0.35, color=color.cyan, parent=self)
        self.subtitle = Text(text="3D Subspace Tactical Chess", scale=1.5, origin=(0, 0), y=0.27, color=color.gray, parent=self)

        self.menu_panel = Entity(parent=self)
        self.btn_ai = Button(text="Игра против ИИ", color=color.azure, scale=(0.4, 0.06), y=0.08, parent=self.menu_panel, on_click=self.start_vs_ai)
        self.btn_host = Button(text="Создать Сетевое Лобби", color=color.azure, scale=(0.4, 0.06), y=0.0, parent=self.menu_panel, on_click=self.open_host_menu)
        self.btn_join = Button(text="Найти Игру по Сети", color=color.azure, scale=(0.4, 0.06), y=-0.08, parent=self.menu_panel, on_click=self.open_lobby_browser)
        self.btn_leaderboard = Button(text="Таблица Лидеров", color=color.azure, scale=(0.4, 0.06), y=-0.16, parent=self.menu_panel, on_click=self.open_leaderboard)
        self.btn_exit = Button(text="Выход", color=color.black66, scale=(0.4, 0.06), y=-0.24, parent=self.menu_panel, on_click=application.quit)

        # Кастомизация
        self.custom_panel = Entity(parent=self.menu_panel, position=(0.5, 0))
        Text(text="ЦВЕТ ФРАКЦИИ:", scale=1.2, position=(0.4, 0.12), parent=self.custom_panel, color=color.light_gray)
        self.btn_c1 = Button(text="Неон", color=color.cyan, scale=(0.1, 0.04), position=(0.35, 0.05), parent=self.custom_panel, on_click=lambda: self.set_faction_color(color.cyan))
        self.btn_c2 = Button(text="Плазма", color=color.magenta, scale=(0.1, 0.04), position=(0.47, 0.05), parent=self.custom_panel, on_click=lambda: self.set_faction_color(color.magenta))
        self.btn_c3 = Button(text="Изумруд", color=color.lime, scale=(0.1, 0.04), position=(0.59, 0.05), parent=self.custom_panel, on_click=lambda: self.set_faction_color(color.lime))
        self.btn_c4 = Button(text="Классика", color=color.white, scale=(0.1, 0.04), position=(0.71, 0.05), parent=self.custom_panel, on_click=lambda: self.set_faction_color(color.white))
        self.preview_sphere = Entity(model='sphere', color=self.faction_color, position=(1.2, 1.0, 2), scale=0.4)

        # Лидерборд
        self.leaderboard_panel = Entity(parent=self, enabled=False)
        self.lead_title = Text(text="РЕЙТИНГ КВАНТОВЫХ СЕКТОРОВ", scale=2, position=(-0.3, 0.3), parent=self.leaderboard_panel, color=color.gold)
        self.lead_text = Text(text="", scale=1.3, position=(-0.2, 0.15), parent=self.leaderboard_panel)
        self.btn_lead_back = Button(text="Назад", color=color.red, scale=(0.15, 0.05), position=(-0.4, -0.3), parent=self.leaderboard_panel, on_click=self.back_from_lead)

        # Браузер лобби
        self.lobby_panel = Entity(parent=self, enabled=False)
        self.lobby_list_text = Text(text="Поиск активных секторов...", scale=1.5, position=(-0.4, 0.1), parent=self.lobby_panel)
        self.btn_back = Button(text="Назад", color=color.red, scale=(0.2, 0.05), position=(-0.4, -0.3), parent=self.lobby_panel, on_click=self.back_to_main)

    def set_faction_color(self, selected_color):
        self.faction_color = selected_color
        self.preview_sphere.color = selected_color
        self.laser_color = color.yellow if selected_color == color.cyan else color.cyan
        print(f"[CUSTOM] Цвет: {selected_color}")

    def start_vs_ai(self):
        self.disable()
        self.preview_sphere.disable()
        self.game.player_custom_color = self.faction_color
        self.game.start_singleplayer_game()

    def open_host_menu(self):
        self.game.network.start_as_host()
        room_id = f"Sector_{random.randint(100, 999)}"
        register_room_on_master(room_name=room_id, game_port=5555)
        self.title.text = f"ОЖИДАНИЕ ИГРОКА В {room_id}"
        self.menu_panel.disable()
        self.preview_sphere.disable()

    def open_lobby_browser(self):
        self.menu_panel.disable()
        self.preview_sphere.disable()
        self.lobby_panel.enable()
        rooms = fetch_rooms_from_master()
        self.lobby_list_text.text = ""
        if not rooms:
            self.lobby_list_text.text = "Свободных секторов не найдено."
            return
        for idx, (room_name, network_info) in enumerate(rooms.items()):
            ip, port = network_info
            btn = Button(
                text=f"Вход в: {room_name} ({ip})",
                scale=(0.5, 0.05),
                y=0.1 - (idx * 0.07),
                parent=self.lobby_panel,
                color=color.dark_gray
            )
            btn.on_click = Func(self.connect_to_room, ip, port)

    def connect_to_room(self, ip, port):
        self.lobby_panel.disable()
        self.disable()
        self.game.player_custom_color = self.faction_color
        self.game.network.connect_to_host(ip, port)

    def open_leaderboard(self):
        self.menu_panel.disable()
        self.preview_sphere.disable()
        self.leaderboard_panel.enable()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect((MASTER_SERVER_IP, MASTER_SERVER_PORT))
            s.sendall(json.dumps({"action": "get_leaderboard"}).encode('utf-8'))
            res = json.loads(s.recv(4096).decode('utf-8'))
            s.close()
            lines = []
            for idx, p in enumerate(res.get("leaderboard", [])):
                lines.append(f"{idx+1}. {p['player'].ljust(20)} — ELO: {p['rating']}")
            self.lead_text.text = "\n".join(lines)
        except Exception:
            self.lead_text.text = "Не удалось загрузить данные."

    def back_from_lead(self):
        self.leaderboard_panel.disable()
        self.menu_panel.enable()
        self.preview_sphere.enable()

    def back_to_main(self):
        self.lobby_panel.disable()
        self.menu_panel.enable()
        self.preview_sphere.enable()
        self.title.text = "SPHERES OF POWER"


# ==========================================
# ОСНОВНОЙ ИГРОВОЙ КЛАСС (3D)
# ==========================================

class Game3D(UrsinaClass):  # <-- Используем явно импортированный класс
    def __init__(self):
        super().__init__()
        window.title = "Spheres of Power - 3D Chess"
        window.borderless = False
        window.exit_button.visible = False

        self.board_logic = Board()
        self.selected_piece_logic = None
        self.visual_pieces = {}
        self.turn = 'white'
        self.game_active = True
        self.player_custom_color = color.cyan

        self.network = NetworkManager(self)
        self.chat_ui = ChatUI(self)
        self.ai = None

        # Блиц-таймеры
        self.blitz_enabled = True
        self.time_white = 180.0
        self.time_black = 180.0
        self.timer_ui_white = Text(text="WHITE: 03:00", position=(0.65, 0.45), scale=1.5, color=color.white)
        self.timer_ui_black = Text(text="BLACK: 03:00", position=(0.65, 0.40), scale=1.5, color=color.gray)

        self.main_menu = MainMenu(self)
        self.menu_visible = True

        camera.position = (12, 16, -14)
        camera.rotation = (35, -35, 0)
        EditorCamera()

        self.create_grid_environment()
        self.render_all_pieces()

        # Звуки (если есть)
        self.snd_move = Audio(resource_path('assets/move_click.wav'), autoplay=False, volume=0.4) if os.path.exists(resource_path('assets/move_click.wav')) else None
        self.snd_laser = Audio(resource_path('assets/laser_beam.wav'), autoplay=False, volume=0.5) if os.path.exists(resource_path('assets/laser_beam.wav')) else None
        self.snd_explosion = Audio(resource_path('assets/quantum_explosion.wav'), autoplay=False, volume=0.8) if os.path.exists(resource_path('assets/quantum_explosion.wav')) else None
        self.snd_ambient = Audio(resource_path('assets/space_ambient.mp3'), loop=True, autoplay=True, volume=0.2) if os.path.exists(resource_path('assets/space_ambient.mp3')) else None

    # ---------- ГРИД ----------
    def create_grid_environment(self):
        self.grid_cells = []
        for z in range(8):
            for y in range(8):
                for x in range(8):
                    if (x + y) % 2 == 0:
                        base_rgba = color.rgba(60, 120, 180, 40)
                    else:
                        base_rgba = color.rgba(20, 20, 20, 15)
                    cell = Button(
                        parent=scene,
                        position=(x, z * 2.0, y),
                        model='cube',
                        scale=0.95,
                        color=base_rgba,
                        shader=cube_transparency_shader if cube_transparency_shader else None
                    )
                    if cube_transparency_shader:
                        cell.set_shader_input('base_color', base_rgba)
                        cell.set_shader_input('cell_layer', float(z))
                        cell.set_shader_input('active_layer', 0.0)
                    cell.coordinates = (x, y, z)
                    cell.on_click = Func(self.on_cell_clicked, cell)
                    cell.on_mouse_enter = Func(self.update_layer_focus, z)
                    self.grid_cells.append(cell)

        # Текстовые метки слоёв
        letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        for z in range(8):
            for i in range(8):
                Text3D(text=f"{letters[i]}:{z}", position=(i, z*2.0, -1), scale=0.4, color=color.lime if z==0 else color.gray)
                Text3D(text=f"{i+1}:{z}", position=(-1, z*2.0, i), scale=0.4, color=color.lime if z==0 else color.gray)

    def update_layer_focus(self, layer_index):
        if cube_transparency_shader:
            for cell in self.grid_cells:
                cell.set_shader_input('active_layer', float(layer_index))

    # ---------- ОТРИСОВКА ФИГУР ----------
    def render_all_pieces(self):
        for vp in self.visual_pieces.values():
            destroy(vp)
        self.visual_pieces.clear()

        for p in self.board_logic.pieces:
            if p.color == 'white':
                m_color = self.player_custom_color if (self.ai is None or self.turn == 'white') else color.white
            else:
                m_color = color.black
            model_name = 'sphere' if p.name == 'P' else 'cube' if p.name == 'R' else 'diamond'
            visual = Entity(
                model=model_name,
                color=m_color,
                position=(p.x, p.z * 2.0, p.y),
                scale=0.6
            )
            Text(text=p.name, parent=visual, scale=5, color=color.red, position=(-0.2, 0.6, 0))
            self.visual_pieces[p] = visual

    # ---------- ОБРАБОТКА КЛИКОВ ----------
    def on_cell_clicked(self, cell):
        if not self.game_active or self.menu_visible:
            return
        if self.network.conn and self.turn != self.network.my_color:
            print("[NET] Не ваш ход.")
            return

        cx, cy, cz = cell.coordinates
        clicked = self.board_logic.get_piece_at(cx, cy, cz)

        if clicked and clicked.color == self.turn:
            self.selected_piece_logic = clicked
            for p, vp in self.visual_pieces.items():
                vp.color = self.player_custom_color if p.color == 'white' else color.black
            self.visual_pieces[clicked].color = color.yellow
            print(f"Выбрана {clicked.name} на ({cx},{cy},{cz})")
            return

        if self.selected_piece_logic:
            if self.board_logic.is_valid_move(cx, cy, cz, self.board_logic):
                is_capture = self.board_logic.get_piece_at(cx, cy, cz) is not None
                self.execute_move(self.selected_piece_logic, cx, cy, cz, is_capture)
                if self.network.conn:
                    self.network.send_move(
                        self.selected_piece_logic.x, self.selected_piece_logic.y, self.selected_piece_logic.z,
                        cx, cy, cz
                    )
                self.selected_piece_logic = None
                self.turn = 'black' if self.turn == 'white' else 'white'

                if self.ai and self.turn == self.ai.ai_color:
                    invoke(self.ai_turn, delay=0.5)
            else:
                print("⛔ Невалидный ход!")

    def execute_move(self, piece, tx, ty, tz, is_capture=False):
        if self.snd_move:
            self.snd_move.play()
        # Исправленная передача координат с умножением z на 2.0
        self.spawn_laser_beam((piece.x, piece.z * 2.0, piece.y), (tx, tz * 2.0, ty), color.cyan if self.turn == 'white' else color.magenta)

        # Квантовый взрыв пешки
        if piece.name == 'P':
            if (piece.color == 'white' and tz == 7) or (piece.color == 'black' and tz == 0):
                self.trigger_quantum_explosion(tx, ty, tz)
                return

        self.board_logic.move_piece(piece, tx, ty, tz)
        self.render_all_pieces()

    def execute_network_move(self, fx, fy, fz, tx, ty, tz):
        piece = self.board_logic.get_piece_at(fx, fy, fz)
        if piece:
            self.board_logic.move_piece(piece, tx, ty, tz)
            self.render_all_pieces()
            self.turn = 'black' if self.turn == 'white' else 'white'
            if self.snd_move:
                self.snd_move.play()

    # ---------- ЛАЗЕР ----------
    def spawn_laser_beam(self, start, end, beam_color=color.cyan):
        p1 = Vec3(start[0], start[1], start[2])
        p2 = Vec3(end[0], end[1], end[2])
        distance = (p2 - p1).length()
        midpoint = (p1 + p2) / 2
        laser = Entity(
            model='cylinder',
            color=beam_color,
            position=midpoint,
            scale=(0.05, distance, 0.05),
            always_on_top=True
        )
        laser.look_at(p2)
        laser.rotation_x += 90
        laser.animate_color(color.rgba(0,0,0,0), duration=1.5, delay=0.5, curve=curve.linear)
        destroy(laser, delay=2.0)
        if self.snd_laser:
            self.snd_laser.play()

    # ---------- КВАНТОВЫЙ ВЗРЫВ ----------
    def trigger_quantum_explosion(self, cx, cy, cz):
        center = Vec3(cx, cz * 2.0, cy)
        wave = Entity(model='sphere', color=color.rgba(255,69,0,180), position=center, scale=0.1)
        wave.animate_scale(Vec3(3,6,3), duration=0.4, curve=curve.out_expo)
        wave.animate_color(color.rgba(0,0,0,0), duration=0.5, delay=0.2)
        destroy(wave, delay=1.0)

        for _ in range(25):
            particle = Entity(
                model='cube',
                color=random.choice([color.yellow, color.orange, color.red]),
                position=center + Vec3(random.uniform(-0.2,0.2), random.uniform(-0.2,0.2), random.uniform(-0.2,0.2)),
                scale=random.uniform(0.05,0.15)
            )
            target = particle.position + Vec3(random.uniform(-2,2), random.uniform(-2,2), random.uniform(-2,2))
            particle.animate_position(target, duration=0.6, curve=curve.out_quad)
            destroy(particle, delay=0.6)

        destroyed = []
        for p in list(self.board_logic.pieces):
            if abs(p.x - cx) <= 1 and abs(p.y - cy) <= 1 and abs(p.z - cz) <= 1:
                destroyed.append(p)
        for p in destroyed:
            if p in self.visual_pieces:
                self.visual_pieces[p].animate_scale(0, duration=0.3)
            self.board_logic.pieces.remove(p)
        if self.snd_explosion:
            self.snd_explosion.play()
        invoke(self.render_all_pieces, delay=0.4)

    # ---------- ХОД ИИ ----------
    def ai_turn(self):
        if self.ai and self.turn == self.ai.ai_color and self.game_active:
            piece, tx, ty, tz = self.ai.make_move(self.board_logic)
            if piece:
                self.execute_move(piece, tx, ty, tz)
                self.turn = 'black' if self.turn == 'white' else 'white'
                self.render_all_pieces()
                if self.turn == self.ai.ai_color:
                    invoke(self.ai_turn, delay=0.5)

    # ---------- ТАЙМЕРЫ ----------
    def update(self):
        if not self.blitz_enabled or not self.game_active or self.menu_visible:
            return
        if self.turn == 'white':
            self.time_white -= time.dt
            if self.time_white <= 0:
                self.time_white = 0
                self.end_game_by_timeout('white')
        else:
            self.time_black -= time.dt
            if self.time_black <= 0:
                self.time_black = 0
                self.end_game_by_timeout('black')

        self.timer_ui_white.text = f"WHITE: {self.format_time(self.time_white)}"
        self.timer_ui_black.text = f"BLACK: {self.format_time(self.time_black)}"
        self.timer_ui_white.color = color.lime if self.turn == 'white' else color.white
        self.timer_ui_black.color = color.lime if self.turn == 'black' else color.gray

    def format_time(self, seconds):
        m = int(seconds) // 60
        s = int(seconds) % 60
        return f"{m:02d}:{s:02d}"

    def end_game_by_timeout(self, loser_color):
        self.game_active = False
        winner = "ЧЁРНЫЕ" if loser_color == 'white' else "БЕЛЫЕ"
        Text(text=f"ВРЕМЯ ИСТЕКЛО!\nПобедили {winner}", position=(0,0), origin=(0,0), scale=3, color=color.gold)
        print(f"[GAME OVER] {loser_color} проиграл по времени.")

    def start_singleplayer_game(self):
        self.menu_visible = False
        self.main_menu.disable()
        self.ai = ChessAI('black')
        self.turn = 'white'
        self.game_active = True
        self.time_white = 180.0
        self.time_black = 180.0

    def input(self, key):
        if key == 'enter':
            self.chat_ui.toggle_chat()


# ==========================================
# ТЕСТЫ (QA)
# ==========================================

class TestSpheresOfPower(unittest.TestCase):
    def setUp(self):
        self.board = Board()

    def test_initial_setup_count(self):
        self.assertEqual(len(self.board.pieces), 52)

    def test_get_piece_at_coordinates(self):
        king = self.board.get_piece_at(4, 0, 0)
        self.assertIsNotNone(king)
        self.assertEqual(king.name, 'K')
        self.assertEqual(king.color, 'white')

    def test_rook_3d_move_logic(self):
        test_board = Board()
        test_board.pieces.clear()
        rook = Piece('R', 'white', 3, 3, 3)
        test_board.pieces.append(rook)
        self.assertTrue(rook.is_valid_move(3, 3, 6, test_board))
        self.assertTrue(rook.is_valid_move(7, 3, 3, test_board))
        self.assertFalse(rook.is_valid_move(4, 4, 4, test_board))

    def test_friendly_fire_block(self):
        rook = self.board.get_piece_at(0, 0, 0)
        self.assertFalse(rook.is_valid_move(0, 1, 0, self.board))

    def test_knight_move(self):
        test_board = Board()
        test_board.pieces.clear()
        knight = Piece('N', 'white', 4, 4, 4)
        test_board.pieces.append(knight)
        self.assertTrue(knight.is_valid_move(6, 5, 4, test_board))
        self.assertTrue(knight.is_valid_move(3, 5, 4, test_board))
        self.assertFalse(knight.is_valid_move(5, 5, 4, test_board))
        self.assertTrue(knight.is_valid_move(6, 4, 5, test_board))
        self.assertFalse(knight.is_valid_move(6, 6, 4, test_board))


def run_backend_tests():
    print("\n[QA] Запуск тестов...")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSpheresOfPower)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("[QA] Все тесты пройдены.")
    else:
        print("[QA] Ошибки!")


if __name__ == "__main__":
    run_backend_tests()
    print("[SYSTEM] Запуск 3D-приложения...")
    app = Game3D()
    app.run()
