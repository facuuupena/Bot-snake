import json
import socket
import sys
import threading
import tkinter as tk
from tkinter import ttk

class NativeSnakeVisualizer:
    def __init__(self, root):
        self.root = root
        self.root.title("🎮 Snake Bot - Visualizador Nativo Ultraliviano")
        self.root.geometry("1000x700")
        self.root.configure(bg="#121212")

        self.games = {}  # {game_id: game_state_dict}
        self.active_game_id = "GRID"  # "GRID" o game_id específico

        self._setup_ui()
        self._start_ipc_server()

    def _setup_ui(self):
        # 1. Barra Superior de Control y Pestañas de Batallas
        self.top_frame = tk.Frame(self.root, bg="#1E1E1E", height=45)
        self.top_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        self.btn_grid = tk.Button(
            self.top_frame,
            text="📺 Vista Multitablero",
            font=("Segoe UI", 10, "bold"),
            bg="#2D2D2D",
            fg="#00E5FF",
            activebackground="#00E5FF",
            activeforeground="#000000",
            relief=tk.FLAT,
            padx=10,
            command=lambda: self.select_game("GRID")
        )
        self.btn_grid.pack(side=tk.LEFT, padx=5, pady=5)

        self.tabs_frame = tk.Frame(self.top_frame, bg="#1E1E1E")
        self.tabs_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 2. Área Principal (Contenedor de Tableros)
        self.main_container = tk.Frame(self.root, bg="#121212")
        self.main_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 3. Barra de Estado Inferior
        self.status_bar = tk.Label(
            self.root,
            text="🟢 Esperando partidas en vivo...",
            font=("Segoe UI", 10),
            bg="#1E1E1E",
            fg="#AAAAAA",
            anchor="w",
            padx=10,
            pady=5
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def select_game(self, game_id):
        self.active_game_id = game_id
        self.render()

    def update_tabs(self):
        for child in self.tabs_frame.winfo_children():
            child.destroy()

        for g_id, g_data in self.games.items():
            p1 = g_data.get('player_1', 'P1')
            p2 = g_data.get('player_2', 'P2')
            short_id = g_id[:6]
            label_text = f"🎮 {p1} vs {p2} ({short_id})"
            
            is_active = (g_id == self.active_game_id)
            btn = tk.Button(
                self.tabs_frame,
                text=label_text,
                font=("Segoe UI", 9, "bold" if is_active else "normal"),
                bg="#00E5FF" if is_active else "#2D2D2D",
                fg="#000000" if is_active else "#FFFFFF",
                relief=tk.FLAT,
                padx=8,
                command=lambda gid=g_id: self.select_game(gid)
            )
            btn.pack(side=tk.LEFT, padx=3)

    def render(self):
        # Limpiar contenedor principal
        for child in self.main_container.winfo_children():
            child.destroy()

        if not self.games:
            lbl = tk.Label(
                self.main_container,
                text="🟢 Esperando que inicien partidas...\nLas peleas aparecerán aquí en vivo sin usar navegador web.",
                font=("Segoe UI", 14),
                bg="#121212",
                fg="#666666"
            )
            lbl.pack(expand=True)
            return

        if self.active_game_id == "GRID" or self.active_game_id not in self.games:
            # Vista Multitablero en Grilla (2x2, 3x3)
            grid_frame = tk.Frame(self.main_container, bg="#121212")
            grid_frame.pack(fill=tk.BOTH, expand=True)

            active_games_list = list(self.games.values())
            num_games = len(active_games_list)
            cols_count = 2 if num_games <= 4 else 3

            for idx, g_data in enumerate(active_games_list):
                r = idx // cols_count
                c = idx % cols_count

                card = tk.Frame(grid_frame, bg="#1E1E1E", bd=1, relief=tk.SOLID)
                card.grid(row=r, column=c, padx=5, pady=5, sticky="nsew")
                grid_frame.grid_rowconfigure(r, weight=1)
                grid_frame.grid_columnconfigure(c, weight=1)

                self._draw_single_game_card(card, g_data, compact=True)
        else:
            # Vista Detallada de 1 Sola Pelea
            g_data = self.games[self.active_game_id]
            card = tk.Frame(self.main_container, bg="#1E1E1E")
            card.pack(fill=tk.BOTH, expand=True)
            self._draw_single_game_card(card, g_data, compact=False)

    def _draw_single_game_card(self, parent, g_data, compact=False):
        p1 = g_data.get('player_1', 'P1')
        p2 = g_data.get('player_2', 'P2')
        s1 = g_data.get('score_1', 0)
        s2 = g_data.get('score_2', 0)
        m1 = g_data.get('multiplier_1', 1)
        m2 = g_data.get('multiplier_2', 1)
        side = g_data.get('side', 'A')
        board_str = g_data.get('board', '')

        # Encabezado
        header = tk.Frame(parent, bg="#252525")
        header.pack(fill=tk.X, padx=2, pady=2)

        my_score = s1 if side == 'A' else s2
        opp_score = s2 if side == 'A' else s1
        status_txt = "🏆 GANANDO" if my_score > opp_score else ("🔴 PERDIENDO" if my_score < opp_score else "⚖️ EMPATE")

        title = f"{p1} ({s1} pts | x{m1})  vs  {p2} ({s2} pts | x{m2})  [{status_txt}]"
        lbl_title = tk.Label(header, text=title, font=("Segoe UI", 10 if compact else 12, "bold"), bg="#252525", fg="#00E5FF")
        lbl_title.pack(side=tk.LEFT, padx=5, pady=2)

        # Lienzo Canvas para dibujar el tablero
        canvas = tk.Canvas(parent, bg="#181818", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        lines = [line.strip() for line in board_str.splitlines() if line.strip()]
        if not lines:
            return

        rows = len(lines)
        cols = max(len(l.strip('|')) for l in lines)

        # Ajustar dimensiones de celda según espacio del Canvas
        canvas.update_idletasks()
        cw = canvas.winfo_width() or (300 if compact else 500)
        ch = canvas.winfo_height() or (300 if compact else 500)

        cell_w = max(10, cw // max(1, cols))
        cell_h = max(10, ch // max(1, rows))
        cell_size = min(cell_w, cell_h)

        offset_x = max(0, (cw - (cols * cell_size)) // 2)
        offset_y = max(0, (ch - (rows * cell_size)) // 2)

        for y, raw_line in enumerate(lines):
            clean_line = raw_line.strip('|')
            for x, char in enumerate(clean_line):
                x1 = offset_x + (x * cell_size)
                y1 = offset_y + (y * cell_size)
                x2 = x1 + cell_size
                y2 = y1 + cell_size

                color = "#222222"  # Espacio vacío
                outline = "#333333"

                if char == 'A':
                    color = "#00FF66"  # Cabeza A (Verde Neón)
                elif char == 'a':
                    color = "#009933"  # Cuerpo a (Verde)
                elif char == 'B':
                    color = "#00E5FF"  # Cabeza B (Cian Neón)
                elif char == 'b':
                    color = "#0055FF"  # Cuerpo b (Azul)
                elif char in ('x', 'X'):
                    color = "#E040FB"  # Multiplicador 'X' (Púrpura)
                elif char == '#':
                    color = "#FF1744"  # Paredes dinámicas v5 (Rojo Carmesí)

                canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline=outline)

                # Texto para números de comida 1..9 o *
                if char.isdigit():
                    canvas.create_rectangle(x1, y1, x2, y2, fill="#FFD700", outline="#B8860B")
                    canvas.create_text(x1 + cell_size//2, y1 + cell_size//2, text=char, fill="#000000", font=("Segoe UI", max(8, cell_size//2), "bold"))
                elif char == '*':
                    canvas.create_oval(x1+2, y1+2, x2-2, y2-2, fill="#FF5252", outline="")

    def handle_incoming_event(self, event_data):
        ev_type = event_data.get('event')
        data = event_data.get('data', {})
        g_id = data.get('game_id')

        if not g_id:
            return

        if ev_type in ('your_turn', 'challenge', 'game_over'):
            if g_id not in self.games:
                self.games[g_id] = {}

            self.games[g_id].update(data)
            self.games[g_id]['game_id'] = g_id
            self.games[g_id]['last_event'] = ev_type

            if ev_type == 'game_over':
                self.games[g_id]['finished'] = True

            self.root.after(0, self._refresh_ui)

    def _refresh_ui(self):
        self.update_tabs()
        self.render()
        num_g = len(self.games)
        self.status_bar.config(text=f"🟢 {num_g} pelea(s) activa(s) | Presiona 'Vista Multitablero' para ver todas juntas.")

    def _start_ipc_server(self):
        def server_loop():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("localhost", 8766))
                sock.listen(5)
                while True:
                    conn, _ = sock.accept()
                    threading.Thread(target=self._handle_client_conn, args=(conn,), daemon=True).start()
            except Exception as e:
                print(f"Error servidor IPC visualizador: {e}")

        threading.Thread(target=server_loop, daemon=True).start()

    def _handle_client_conn(self, conn):
        buffer = ""
        while True:
            try:
                chunk = conn.recv(4096).decode('utf-8')
                if not chunk:
                    break
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.strip():
                        data = json.loads(line.strip())
                        self.handle_incoming_event(data)
            except Exception:
                break
        conn.close()

if __name__ == '__main__':
    root = tk.Tk()
    app = NativeSnakeVisualizer(root)
    root.mainloop()
