import json
import socket
import sys
import threading
import tkinter as tk
from tkinter import ttk

class NativeSnakeVisualizer:
    def __init__(self, root):
        self.root = root
        self.root.title("🎮 Snake Bot - Visualizador Nativo Fluido (Sin Parpadeo)")
        self.root.geometry("1100x750")
        self.root.configure(bg="#121212")

        self.games = {}  # {game_id: game_state_dict}
        self.active_game_id = "GRID"  # "GRID" o game_id específico

        # Estructura persistente para evitar destruir y recrear widgets (Cero Parpadeo / Flickering)
        self.card_widgets = {}  # {game_id: {'frame': card, 'canvas': canvas, 'lbl_title': label, 'lbl_info': label}}
        self.tab_buttons = {}   # {game_id: button}

        self._setup_ui()
        self._start_ipc_server()

    def _setup_ui(self):
        # 1. Barra Superior de Control y Pestañas de Batallas
        self.top_frame = tk.Frame(self.root, bg="#1E1E1E", height=50)
        self.top_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        self.btn_grid = tk.Button(
            self.top_frame,
            text="📺 Vista Multitablero",
            font=("Segoe UI", 10, "bold"),
            bg="#00E5FF",
            fg="#000000",
            activebackground="#00B2CC",
            activeforeground="#000000",
            relief=tk.FLAT,
            padx=12,
            pady=4,
            command=lambda: self.select_game("GRID")
        )
        self.btn_grid.pack(side=tk.LEFT, padx=5, pady=5)

        self.tabs_container = tk.Frame(self.top_frame, bg="#1E1E1E")
        self.tabs_container.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 2. Leyenda explicativa superior
        legend_frame = tk.Frame(self.root, bg="#181818", pady=3)
        legend_frame.pack(side=tk.TOP, fill=tk.X, padx=5)

        tk.Label(legend_frame, text=" Leyenda: ", font=("Segoe UI", 9, "bold"), bg="#181818", fg="#888888").pack(side=tk.LEFT, padx=2)
        tk.Label(legend_frame, text="🟩 Tu Serpiente (A)", font=("Segoe UI", 9, "bold"), bg="#181818", fg="#00FF66").pack(side=tk.LEFT, padx=6)
        tk.Label(legend_frame, text="🟦 Rival (B)", font=("Segoe UI", 9, "bold"), bg="#181818", fg="#00E5FF").pack(side=tk.LEFT, padx=6)
        tk.Label(legend_frame, text="🟨 Comida (1-9)", font=("Segoe UI", 9, "bold"), bg="#181818", fg="#FFD700").pack(side=tk.LEFT, padx=6)
        tk.Label(legend_frame, text="🟪 Multiplicador (X)", font=("Segoe UI", 9, "bold"), bg="#181818", fg="#E040FB").pack(side=tk.LEFT, padx=6)
        tk.Label(legend_frame, text="🟥 Pared Láser (#)", font=("Segoe UI", 9, "bold"), bg="#181818", fg="#FF1744").pack(side=tk.LEFT, padx=6)

        # 3. Área Principal (Contenedor Persistente de Tableros)
        self.main_container = tk.Frame(self.root, bg="#121212")
        self.main_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Mensaje de bienvenida inicial
        self.empty_label = tk.Label(
            self.main_container,
            text="🟢 Esperando que inicien partidas...\nLas peleas aparecerán aquí en vivo con renderizado fluido.",
            font=("Segoe UI", 14),
            bg="#121212",
            fg="#666666"
        )
        self.empty_label.pack(expand=True)

        # 4. Barra de Estado Inferior
        self.status_bar = tk.Label(
            self.root,
            text="🟢 Servidor de renderizado fluido listo. Esperando eventos de juego...",
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
        self._update_tab_buttons_style()
        self.rebuild_layout()

    def _update_tab_buttons_style(self):
        self.btn_grid.config(
            bg="#00E5FF" if self.active_game_id == "GRID" else "#2D2D2D",
            fg="#000000" if self.active_game_id == "GRID" else "#FFFFFF"
        )
        for g_id, btn in self.tab_buttons.items():
            is_act = (g_id == self.active_game_id)
            btn.config(
                bg="#00E5FF" if is_act else "#2D2D2D",
                fg="#000000" if is_act else "#FFFFFF",
                font=("Segoe UI", 9, "bold" if is_act else "normal")
            )

    def update_tabs(self):
        # Crear nuevos botones de pestaña solo si no existen
        for g_id, g_data in list(self.games.items()):
            if g_id not in self.tab_buttons:
                p1 = g_data.get('player_1', 'P1')
                p2 = g_data.get('player_2', 'P2')
                short_id = g_id[:6]
                label_text = f"🎮 {p1} vs {p2} ({short_id})"

                btn = tk.Button(
                    self.tabs_container,
                    text=label_text,
                    font=("Segoe UI", 9),
                    bg="#2D2D2D",
                    fg="#FFFFFF",
                    relief=tk.FLAT,
                    padx=8,
                    pady=2,
                    command=lambda gid=g_id: self.select_game(gid)
                )
                btn.pack(side=tk.LEFT, padx=3)
                self.tab_buttons[g_id] = btn

        self._update_tab_buttons_style()

    def rebuild_layout(self):
        # Ocultar todos los cards existentes sin destruirlos
        for g_id, widgets in self.card_widgets.items():
            widgets['frame'].pack_forget()
            widgets['frame'].grid_forget()

        if not self.games:
            self.empty_label.pack(expand=True)
            return
        else:
            self.empty_label.pack_forget()

        if self.active_game_id == "GRID" or self.active_game_id not in self.games:
            active_games_list = list(self.games.keys())
            num_games = len(active_games_list)
            cols_count = 2 if num_games <= 4 else 3

            for idx, g_id in enumerate(active_games_list):
                r = idx // cols_count
                c = idx % cols_count

                widgets = self._get_or_create_card(g_id)
                widgets['frame'].grid(row=r, column=c, padx=5, pady=5, sticky="nsew")
                self.main_container.grid_rowconfigure(r, weight=1)
                self.main_container.grid_columnconfigure(c, weight=1)
                self.update_card_render(g_id, compact=True)
        else:
            widgets = self._get_or_create_card(self.active_game_id)
            widgets['frame'].pack(fill=tk.BOTH, expand=True)
            self.update_card_render(self.active_game_id, compact=False)

    def _get_or_create_card(self, g_id):
        if g_id in self.card_widgets:
            return self.card_widgets[g_id]

        card = tk.Frame(self.main_container, bg="#1E1E1E", bd=1, relief=tk.SOLID)

        # Header Frame
        header = tk.Frame(card, bg="#252525")
        header.pack(fill=tk.X, padx=2, pady=2)

        lbl_title = tk.Label(header, text="", font=("Segoe UI", 11, "bold"), bg="#252525", fg="#00E5FF")
        lbl_title.pack(side=tk.TOP, anchor="w", padx=5, pady=1)

        lbl_info = tk.Label(header, text="", font=("Segoe UI", 9), bg="#252525", fg="#CCCCCC")
        lbl_info.pack(side=tk.TOP, anchor="w", padx=5, pady=1)

        # Persistent Canvas widget (CERO PARPADEO)
        canvas = tk.Canvas(card, bg="#141414", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        widgets = {
            'frame': card,
            'canvas': canvas,
            'lbl_title': lbl_title,
            'lbl_info': lbl_info
        }
        self.card_widgets[g_id] = widgets
        return widgets

    def update_card_render(self, g_id, compact=False):
        if g_id not in self.games or g_id not in self.card_widgets:
            return

        g_data = self.games[g_id]
        widgets = self.card_widgets[g_id]

        p1 = g_data.get('player_1', 'P1')
        p2 = g_data.get('player_2', 'P2')
        s1 = g_data.get('score_1', 0)
        s2 = g_data.get('score_2', 0)
        m1 = g_data.get('multiplier_1', 1)
        m2 = g_data.get('multiplier_2', 1)
        side = g_data.get('side', 'A')
        board_str = g_data.get('board', '')
        remaining_moves = g_data.get('remaining_moves', 300)

        # Determinar quién es quién (TÚ vs RIVAL)
        is_my_turn_a = (side == 'A')
        my_name = p1 if is_my_turn_a else p2
        my_score = s1 if is_my_turn_a else s2
        my_mult = m1 if is_my_turn_a else m2
        my_color_name = "VERDE" if is_my_turn_a else "AZUL"

        opp_name = p2 if is_my_turn_a else p1
        opp_score = s2 if is_my_turn_a else s1
        opp_mult = m2 if is_my_turn_a else m1
        opp_color_name = "AZUL" if is_my_turn_a else "VERDE"

        diff = my_score - opp_score
        if diff > 0:
            status_txt = f"🏆 GANANDO (+{diff} pts)"
            status_fg = "#00FF66"
        elif diff < 0:
            status_txt = f"🔴 PERDIENDO ({diff} pts)"
            status_fg = "#FF5252"
        else:
            status_txt = "⚖️ EMPATE (0 pts)"
            status_fg = "#FFD700"

        # Encabezado con información detallada de turnos e identidad
        title_text = f"🎮 {p1} ({s1} pts | x{m1})  vs  {p2} ({s2} pts | x{m2})"
        info_text = f"👤 TÚ: {my_name} ({my_color_name}) | ⏳ Turnos restantes: {remaining_moves}/300 | Estado: {status_txt}"

        widgets['lbl_title'].config(text=title_text)
        widgets['lbl_info'].config(text=info_text, fg=status_fg)

        # -------------------------------------------------------------
        # Dibujar Tablero en el Canvas sin destruir el widget
        # -------------------------------------------------------------
        canvas = widgets['canvas']
        canvas.delete("all")  # Limpia los elementos gráficos anteriores instantáneamente sin parpadeo

        lines = [line.strip() for line in board_str.splitlines() if line.strip()]
        if not lines:
            return

        rows = len(lines)
        cols = max(len(l.strip('|')) for l in lines)

        cw = canvas.winfo_width()
        ch = canvas.winfo_height()
        if cw <= 1 or ch <= 1:
            cw = 320 if compact else 600
            ch = 320 if compact else 600

        cell_w = max(8, cw // max(1, cols))
        cell_h = max(8, ch // max(1, rows))
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

                color = "#181818"  # Fondo espacio libre
                outline = "#2A2A2A"

                is_my_head = False
                is_opp_head = False

                if char == 'A':
                    color = "#00FF66"  # Cabeza A
                    if side == 'A': is_my_head = True
                    else: is_opp_head = True
                elif char == 'a':
                    color = "#00B347"  # Cuerpo a
                elif char == 'B':
                    color = "#00E5FF"  # Cabeza B
                    if side == 'B': is_my_head = True
                    else: is_opp_head = True
                elif char == 'b':
                    color = "#0099B8"  # Cuerpo b
                elif char in ('x', 'X'):
                    color = "#E040FB"  # Multiplicador 'X' (Púrpura)
                elif char == '#':
                    color = "#FF1744"  # Paredes dinámicas v5 (Rojo Carmesí)

                # Dibujar celda principal
                canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline=outline)

                # Pared dinámica de la regla v5 (#)
                if char == '#':
                    canvas.create_line(x1, y1, x2, y2, fill="#FFFFFF", width=1)
                    canvas.create_line(x1, y2, x2, y1, fill="#FFFFFF", width=1)

                # Destacar las cabezas con marcas distintas para saber cuál eres tú
                if is_my_head:
                    # Borde dorado reluciente para TU cabeza
                    canvas.create_rectangle(x1+1, y1+1, x2-1, y2-1, outline="#FFD700", width=2)
                    canvas.create_text(x1 + cell_size//2, y1 + cell_size//2, text="👑", font=("Segoe UI", max(7, cell_size//2)))
                elif is_opp_head:
                    # Marca de rival
                    canvas.create_rectangle(x1+1, y1+1, x2-1, y2-1, outline="#FF1744", width=2)
                    canvas.create_text(x1 + cell_size//2, y1 + cell_size//2, text="💀", font=("Segoe UI", max(7, cell_size//2)))

                # Números de comida cíclica 1..9 (v3)
                if char.isdigit():
                    canvas.create_rectangle(x1+1, y1+1, x2-1, y2-1, fill="#FFD700", outline="#B8860B")
                    canvas.create_text(x1 + cell_size//2, y1 + cell_size//2, text=char, fill="#000000", font=("Segoe UI", max(8, cell_size//2), "bold"))
                elif char in ('x', 'X'):
                    canvas.create_text(x1 + cell_size//2, y1 + cell_size//2, text="X", fill="#FFFFFF", font=("Segoe UI", max(8, cell_size//2), "bold"))
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

            self.root.after(0, lambda: self._on_game_updated(g_id))

    def _on_game_updated(self, g_id):
        self.update_tabs()

        if self.active_game_id == "GRID":
            if g_id in self.card_widgets:
                self.update_card_render(g_id, compact=True)
            else:
                self.rebuild_layout()
        elif self.active_game_id == g_id:
            if g_id in self.card_widgets:
                self.update_card_render(g_id, compact=False)
            else:
                self.rebuild_layout()

        num_g = len(self.games)
        self.status_bar.config(text=f"🟢 {num_g} pelea(s) en vivo transmitiendo a 60fps sin parpadeos.")

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
