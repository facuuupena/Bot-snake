import asyncio
import json
import os
from random import randint
import sys
import time
import webbrowser
import websockets


# A running text log of events received / actions sent per game, written to
# game_<game_id>.log when the match ends.
HISTORY = {}
OPENED_GAMES = set()


def log_event(game_id, message):
    HISTORY.setdefault(game_id, []).append('< ' + json.dumps(message))


def log_action(game_id, message):
    HISTORY.setdefault(game_id, []).append('> ' + json.dumps(message))


LOGS_DIR = "logs"


def write_game_log(game_id):
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        filename = f"game_{game_id}.log"
        filepath = os.path.join(LOGS_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(HISTORY.get(game_id, [])) + "\n")
        print(f"saved {filepath}")
    except OSError as e:
        print(f"could not write game log: {e}")



def sanitize_columns(board_str):
    """
    Calcula el número de columnas asegurando que NUNCA se produzcan datos o rangos negativos.
    Previene errores como randint(0, -2) cuando no existe '|'.
    """
    if not isinstance(board_str, str) or not board_str:
        return 0

    first_pipe = board_str.find('|', 1)
    if first_pipe > 1:
        cols = first_pipe - 1
        return max(0, cols)

    lines = [line.strip() for line in board_str.splitlines() if line.strip()]
    if lines:
        cleaned_line = lines[0].replace('|', '').replace(' ', '')
        return max(0, len(cleaned_line) - 1)

    return 0


def clamp_non_negative(value, min_val=0, max_val=1000):
    """Garantiza que un valor sea un entero estrictamente no negativo (>= 0)."""
    try:
        val = int(value)
        return max(min_val, min(val, max_val))
    except (ValueError, TypeError):
        return min_val


LIVE_CLIENTS = set()


async def live_ws_handler(websocket):
    LIVE_CLIENTS.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        LIVE_CLIENTS.discard(websocket)


GUI_PROCESS = None
import socket
import subprocess


def ensure_gui_running():
    """Reabre automáticamente el visualizador Tkinter si el usuario lo cerró sin querer."""
    global GUI_PROCESS
    gui_script = os.path.abspath("gui_visualizer.py")
    if os.path.exists(gui_script) and (GUI_PROCESS is None or GUI_PROCESS.poll() is not None):
        try:
            GUI_PROCESS = subprocess.Popen([sys.executable, gui_script])
            print("🟢 Visualizador Nativo de Escritorio Tkinter iniciado / reabierto")
            time.sleep(0.3)
        except Exception as e:
            print(f"Nota Visualizador Nativo: {e}")


async def broadcast_live_event(message_data):
    msg = json.dumps(message_data)

    # 1. Transmitir a visualizador web si hay clientes abiertos
    if LIVE_CLIENTS:
        for client in list(LIVE_CLIENTS):
            try:
                await client.send(msg)
            except Exception:
                LIVE_CLIENTS.discard(client)

    # 2. Transmitir a Visualizador Nativo de Escritorio Tkinter (localhost:8766)
    def send_to_gui():
        ensure_gui_running()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                s.connect(("localhost", 8766))
                s.sendall((msg + "\n").encode('utf-8'))
        except Exception:
            pass

    asyncio.get_event_loop().run_in_executor(None, send_to_gui)


async def start_live_server():
    ensure_gui_running()
    try:
        async with websockets.serve(live_ws_handler, "localhost", 8765):
            await asyncio.Future()  # mantener servidor abierto
    except Exception as e:
        print(f"Nota: Servidor de transmisión local: {e}")



async def send(websocket, action, data):
    message = json.dumps(
        {
            'action': action,
            'data': data,
        }
    )
    print(message)
    await websocket.send(message)


async def start(auth_token):
    asyncio.create_task(start_live_server())
    uri = "wss://server.codechallenge.net.ar/ws?token={}".format(auth_token)
    # uri = "ws://localhost:5000/ws?token={}".format(auth_token)
    while True:
        try:
            print('connection to {}'.format(uri))
            async with websockets.connect(uri) as websocket:
                print('connection READY!')
                await play(websocket)
        except KeyboardInterrupt:
            print('Exiting...')
            break
        except Exception:
            print('connection error!')
            time.sleep(3)


async def play(websocket):
    while True:
        try:
            request = await websocket.recv()
            print(f"< {request}")
            request_data = json.loads(request)

            # Transmitir en tiempo real al visualizador de navegador
            await broadcast_live_event(request_data)

            if request_data['event'] == 'update_user_list':
                pass
            if request_data['event'] == 'game_over':
                game_id = request_data['data'].get('game_id')
                if game_id:
                    log_event(game_id, request_data)
                    write_game_log(game_id)
            if request_data['event'] == 'challenge':
                # if request_data['data']['opponent'] == 'favoriteopponent':
                await send(
                    websocket,
                    'accept_challenge',
                    {
                        'challenge_id': request_data['data']['challenge_id'],
                    },
                )
            if request_data['event'] == 'your_turn':
                log_event(request_data['data']['game_id'], request_data)
                await process_your_turn(websocket, request_data)
        except KeyboardInterrupt:
            print('Exiting...')
            break
        except Exception as e:
            print('error {}'.format(str(e)))
            break  # force login again


async def process_your_turn(websocket, request_data):
    await process_move(websocket, request_data)


async def process_move(websocket, request_data):
    data = request_data.get('data', {})
    board = data.get('board', '')
    side = data.get('side', 'A')
    game_id = data.get('game_id', '')

    # 1. Sanear y calcular columnas evitando números negativos (SIEMPRE >= 0)
    colums = sanitize_columns(board)

    # 2. Selección de movimiento seguro y no negativo
    if colums > 0:
        raw_col = randint(0, colums)
    else:
        raw_col = 0

    safe_col = clamp_non_negative(raw_col, min_val=0, max_val=max(0, colums))

    # 3. Calcular la dirección oficial de Snake ("up", "down", "left", "right") usando BFS + Flood-Fill
    board_size = data.get('board_size')
    m1 = data.get('multiplier_1', 1)
    m2 = data.get('multiplier_2', 1)
    my_multiplier = m1 if side == 'A' else m2

    snake_move = choose_smart_snake_direction(
        board, side, game_id=game_id, board_size=board_size, my_multiplier=my_multiplier)

    move = {
        'game_id': game_id,
        'turn_token': data.get('turn_token', ''),
        'col': safe_col,
    }

    # Adjuntar 'direction' solo cuando la partida sea Snake (side es 'A'/'B' o indica 'snake'/'direction')
    if 'direction' in data or 'snake' in data or 'head' in data or data.get('game') == 'snake' or side in ('A', 'B'):
        move['direction'] = snake_move

    log_action(move['game_id'], {'action': 'move', 'data': move})
    await send(websocket, 'move', move)


GAME_TARGET_DIGITS = {}
GAME_ACTIVE_TARGET = {}  # {game_id: {'active': 1, 'prev_digits': set()}}
GAME_MULTIPLIERS = {}


def parse_official_snake_board(board_str, my_side='A', board_size=None, game_id=None):
    """
    Parsea la cuadrícula del tablero de Snake de The Code Challenge (v1, v2, v3, v4, v5):
    - 'A' / 'B': Cabezas de las serpientes.
    - 'a' / 'b': Cuerpos de las serpientes.
    - '*': Comida estándar (v1 / v2).
    - '1'..'9': Comida numérica en orden cíclico ascendente (v3).
    - 'x' / 'X': Ítem multiplicador permanente +50 pts (v4).
    - '#': Paredes dinámicas encogibles (v5).
    - ' ': Espacio libre.
    - '|': Bordes laterales del tablero.
    """
    width = 15
    height = 15

    # v2: Parsear board_size dinámico (ej: "14x18" -> rows=14, cols=18)
    if isinstance(board_size, str) and 'x' in board_size.lower():
        parts = board_size.lower().split('x')
        try:
            parsed_r = int(parts[0].strip())
            parsed_c = int(parts[1].strip())
            if parsed_r > 0 and parsed_c > 0:
                height = parsed_r
                width = parsed_c
        except ValueError:
            pass

    if not isinstance(board_str, str) or not board_str:
        return {'head': (0, 0), 'body': [], 'tail': (0, 0), 'opp_head': None, 'opp_body': [], 'obstacles': set(), 'apples': [(5, 5)], 'multipliers': [], 'bad_digits': set(), 'width': width, 'height': height}

    lines = [line.strip() for line in board_str.splitlines() if line.strip()]
    if not lines:
        return {'head': (0, 0), 'body': [], 'tail': (0, 0), 'opp_head': None, 'opp_body': [], 'obstacles': set(), 'apples': [(5, 5)], 'multipliers': [], 'bad_digits': set(), 'width': width, 'height': height}

    height = max(height, len(lines))
    grid_w = 0
    for l in lines:
        cl = l.strip('|')
        grid_w = max(grid_w, len(cl))
    width = max(width, grid_w)

    my_head_char = my_side.upper() if my_side and my_side.upper() in ('A', 'B') else 'A'
    my_body_char = my_head_char.lower()
    opp_head_char = 'B' if my_head_char == 'A' else 'A'
    opp_body_char = opp_head_char.lower()

    head_pos = None
    opp_head = None
    my_body = []
    opp_body = []
    obstacles = set()
    apples = []
    multipliers = []
    digits_found = {}  # {digit_int: (x, y)}

    for y, raw_line in enumerate(lines):
        clean_line = raw_line
        if clean_line.startswith('|'):
            clean_line = clean_line[1:]
        if clean_line.endswith('|'):
            clean_line = clean_line[:-1]

        for x, char in enumerate(clean_line):
            if char == '*':
                apples.append((x, y))
            elif char in ('x', 'X'):
                multipliers.append((x, y))
            elif char.isdigit() and char != '0':
                digit_val = int(char)
                digits_found[digit_val] = (x, y)
            elif char == my_head_char:
                head_pos = (x, y)
            elif char == my_body_char:
                my_body.append((x, y))
                obstacles.add((x, y))
            elif char == opp_head_char:
                opp_head = (x, y)
                obstacles.add((x, y))
            elif char == opp_body_char:
                opp_body.append((x, y))
                obstacles.add((x, y))
            elif char == '#':
                obstacles.add((x, y))  # v5: Pared dinámica '#' (evitación estricta de penalización -500)

    # v3: Rastreador de Secuencia Global Cíclica (Dígitos 1 a 9)
    target_digit = None
    if digits_found:
        if game_id:
            state = GAME_ACTIVE_TARGET.setdefault(game_id, {'active': 1, 'prev_digits': set()})
            curr_active = state['active']

            # Si el dígito activo anterior estaba en el mapa y ya no está, se consumió -> Avanzar secuencia
            if curr_active in state['prev_digits'] and curr_active not in digits_found:
                curr_active = (curr_active % 9) + 1
                state['active'] = curr_active

            # Si el dígito activo no está presente pero hay otros números superiores, sincronizar al menor disponible >= curr_active
            if curr_active not in digits_found:
                valid_candidates = [d for d in digits_found.keys() if d >= curr_active]
                if valid_candidates:
                    curr_active = min(valid_candidates)
                else:
                    curr_active = min(digits_found.keys())
                state['active'] = curr_active

            target_digit = curr_active
            state['prev_digits'] = set(digits_found.keys())
        else:
            target_digit = min(digits_found.keys())

    if target_digit and game_id:
        GAME_TARGET_DIGITS[game_id] = target_digit

    bad_digits = set()
    target_apples = []

    if digits_found:
        for digit_val, pos in digits_found.items():
            if digit_val == target_digit:
                target_apples.append(pos)
            else:
                bad_digits.add(pos)
                obstacles.add(pos)  # Dígitos incorrectos en la secuencia actúan como obstáculos mortales (-500 pts)

    # Prioridad estricta de objetivos: Dígito en secuencia v3 primero (miles de pts), luego multiplicadores 'X', luego manzanas *
    all_targets = target_apples + multipliers + apples

    if head_pos is None:
        head_pos = (0, 0)
    if not all_targets:
        all_targets = [(min(5, width - 1), min(5, height - 1))]

    tail_pos = my_body[-1] if my_body else head_pos

    return {
        'head': head_pos,
        'body': my_body,
        'tail': tail_pos,
        'opp_head': opp_head,
        'opp_body': opp_body,
        'obstacles': obstacles,
        'apples': all_targets,
        'target_pos': target_apples[0] if target_apples else None,
        'multipliers': multipliers,
        'bad_digits': bad_digits,
        'target_digit': target_digit,
        'width': max(1, width),
        'height': max(1, height)
    }


LAST_MOVES = {}
OPPOSITE_MOVES = {
    'up': 'down',
    'down': 'up',
    'left': 'right',
    'right': 'left'
}


def flood_fill_count(start_pos, obstacles, width, height, max_depth=60):
    """
    Cuenta cuántas casillas libres son accesibles desde start_pos.
    Previene meterse en callejones sin salida donde la serpiente se queda atrapada.
    """
    from collections import deque
    queue = deque([start_pos])
    visited = {start_pos}
    count = 0

    while queue and count < max_depth:
        cx, cy = queue.popleft()
        count += 1

        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in obstacles and (nx, ny) not in visited:
                visited.add((nx, ny))
                queue.append((nx, ny))

    return count


def count_escape_corridors(start_pos, obstacles, width, height):
    """
    Calcula el espacio accesible y las salidas abiertas de aire.
    Permite identificar y evitar zonas de estrangulamiento (Choke Points) que el rival pueda cerrar.
    """
    from collections import deque
    queue = deque([start_pos])
    visited = {start_pos}
    reachables = []

    while queue and len(reachables) < 60:
        cx, cy = queue.popleft()
        reachables.append((cx, cy))

        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in obstacles and (nx, ny) not in visited:
                visited.add((nx, ny))
                queue.append((nx, ny))

    # Una salida abierta es una casilla accesible que no está pegada a un borde
    open_exits = sum(1 for rx, ry in reachables if 1 <= rx <
                     width - 1 and 1 <= ry < height - 1)
    return len(reachables), open_exits


def choose_smart_snake_direction(board_str, side='A', game_id=None, board_size=None, my_multiplier=1):
    """
    Algoritmo de Inteligencia Artificial Avanzada Dual (Ofensivo y Defensivo):
    1. Prevención estricta de giros de 180° sobre su propio cuello.
    2. Detección Defensiva de Encierro y Zonas de Estrangulamiento (Choke Points).
    3. Estrategia Ofensiva de Estrangulamiento: Si movernos a una posición recorta el espacio rival < su longitud, realiza el ATAQUE DE ENCIERRO.
    4. Estrategia en 2 Fases:
       - FASE 1 (Multiplicador < 10): Prioridad masiva a multiplicadores 'X' para elevar ganancia temprana.
       - FASE 2 (Multiplicador >= 10): Caza voraz de todos los dígitos en secuencia (1..9) indiferente de su valor, comiendo 'X' de paso si está cerca (<= 4 pasos).
    5. Evita colisiones de cabeza vulnerables con el rival a menos que seamos más largos.
    6. Modo Supervivencia Seguimiento de Cola (Tail-Following) si la manzana es peligrosa.
    """
    parsed = parse_official_snake_board(
        board_str, side, board_size=board_size, game_id=game_id)
    head_x, head_y = parsed['head']
    my_body = parsed['body']
    tail_pos = parsed['tail']
    opp_head = parsed['opp_head']
    opp_body = parsed['opp_body']
    obstacles = parsed['obstacles']
    apples = parsed['apples']
    multipliers_set = set(parsed.get('multipliers', []))
    width = parsed['width']
    height = parsed['height']

    snake_len = len(my_body) + 1
    opp_len = len(opp_body) + 1
    last_move = LAST_MOVES.get(game_id)
    opposite = OPPOSITE_MOVES.get(last_move) if isinstance(last_move, str) else None

    moves = [
        (0, -1, 'up'),
        (0, 1, 'down'),
        (-1, 0, 'left'),
        (1, 0, 'right')
    ]

    valid_moves = []
    for dx, dy, move_name in moves:
        if move_name == opposite:
            continue
        nx, ny = head_x + dx, head_y + dy
        if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in obstacles:
            valid_moves.append((dx, dy, move_name, (nx, ny)))

    if not valid_moves:
        for dx, dy, move_name in moves:
            nx, ny = head_x + dx, head_y + dy
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in obstacles:
                valid_moves.append((dx, dy, move_name, (nx, ny)))

    # Respaldo por Desesperación Inteligente (Smart Panic Emergency Escape)
    if not valid_moves:
        for dx, dy, move_name in moves:
            if move_name == opposite:
                continue
            nx, ny = head_x + dx, head_y + dy
            if (nx, ny) == tail_pos:
                LAST_MOVES[game_id] = move_name
                return move_name

        for dx, dy, move_name in moves:
            nx, ny = head_x + dx, head_y + dy
            if 0 <= nx < width and 0 <= ny < height:
                LAST_MOVES[game_id] = move_name
                return move_name

        return 'up'

    # Identificar movimientos probables de la cabeza rival para no regalarnos
    opp_next_moves = set()
    if opp_head:
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            ox, oy = opp_head[0] + dx, opp_head[1] + dy
            if 0 <= ox < width and 0 <= oy < height and (ox, oy) not in obstacles:
                opp_next_moves.add((ox, oy))

    from collections import deque

    def bfs_find_path(start, target):
        q = deque([(start[0], start[1], [])])
        vis = {start}
        while q:
            cx, cy, path = q.popleft()
            if (cx, cy) == target:
                return path
            for dx, dy, move_name in moves:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in obstacles and (nx, ny) not in vis:
                    vis.add((nx, ny))
                    q.append((nx, ny, path + [move_name]))
        return None

    # 1. ATAQUE OFENSIVO DE ENCIERRO (Trap Attack):
    best_trap_move = None
    if opp_head and snake_len >= opp_len:
        for dx, dy, move_name, pos in valid_moves:
            sim_obstacles = set(obstacles) | {pos}
            opp_space = flood_fill_count(
                opp_head, sim_obstacles, width, height)
            my_space = flood_fill_count(pos, sim_obstacles, width, height)

            if opp_space < opp_len and my_space >= snake_len:
                best_trap_move = move_name
                break

    if best_trap_move:
        LAST_MOVES[game_id] = best_trap_move
        return best_trap_move

    target_pos = parsed.get('target_pos')

    # Estrategia Dinámica Dual por Fases de Multiplicador:
    # FASE 1 (my_multiplier < 10): Crecimiento inicial -> Priorizar multiplicadores 'X' masivamente.
    # FASE 2 (my_multiplier >= 10): Voracidad de Secuencia -> Priorizar TODOS los dígitos (1 al 9) indiferente del valor, y comer 'X' solo "de paso" si está cerca (my_d <= 4).
    is_phase_1 = (my_multiplier < 10)

    candidate_apples = []
    for a in apples:
        path = bfs_find_path((head_x, head_y), a)
        if not path:
            continue
        my_d = len(path)
        opp_d = 999
        if opp_head:
            opp_p = bfs_find_path(opp_head, a)
            if opp_p:
                opp_d = len(opp_p)

        is_target_digit = (target_pos and a == target_pos)

        race_penalty = 0
        target_bonus = 0
        multiplier_bonus = 0

        if is_target_digit:
            if is_phase_1:
                # En Fase 1 (< x10): Dígitos bajos o lejanos dan prioridad a 'X'. Si está muy cerca (<=3), comerlo.
                target_bonus = 5
                if my_d <= 3:
                    target_bonus = 15
            else:
                # En Fase 2 (>= x10): MÁXIMA PRIORIDAD A TODOS LOS DÍGITOS (1 al 9) indiferente del valor
                target_bonus = 35
                if my_d <= 7:
                    target_bonus = 45

                if opp_head and opp_d < my_d:
                    race_penalty = 15

        elif a in multipliers_set:
            if is_phase_1:
                # Fase 1 (< x10): Caza agresiva de 'X' para llegar a x10 rápidamente
                multiplier_bonus = 25
            else:
                # Fase 2 (>= x10): Solo comer 'X' si está "de paso" o muy cerca (my_d <= 4)
                if my_d <= 4:
                    multiplier_bonus = 15
                else:
                    multiplier_bonus = 2

            if opp_head and opp_d < my_d:
                race_penalty = 10

        effective_dist = my_d + race_penalty - target_bonus - multiplier_bonus
        candidate_apples.append((effective_dist, a, path))

    candidate_apples.sort(key=lambda x: x[0])

    for _, a, path in candidate_apples:
        first_move = path[0]
        for dx, dy, move_name, pos in valid_moves:
            if move_name == first_move:
                space, open_exits = count_escape_corridors(
                    pos, obstacles, width, height)
                is_head_danger = (pos in opp_next_moves) and (
                    snake_len <= opp_len)
                # Refuerzo Anti-Encierro estricto: evita trampas y cuellos de botella sin salida
                is_choke = (open_exits <= 1 and space < max(snake_len * 2.0, 18))
                if space >= min(snake_len + 3, 18) and not is_head_danger and not is_choke:
                    LAST_MOVES[game_id] = first_move
                    return first_move

    # 3. Modo Supervivencia: Intentar seguir la propia cola (Tail-Following)
    if tail_pos != (head_x, head_y):
        obstacles_no_tail = set(obstacles)
        obstacles_no_tail.discard(tail_pos)

        tail_queue = deque([(head_x, head_y, [])])
        tail_visited = {(head_x, head_y)}
        tail_path = None
        while tail_queue:
            cx, cy, path = tail_queue.popleft()
            if (cx, cy) == tail_pos:
                tail_path = path
                break
            for dx, dy, move_name in moves:
                if move_name == opposite and len(path) == 0:
                    continue
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in obstacles_no_tail and (nx, ny) not in tail_visited:
                    tail_visited.add((nx, ny))
                    tail_queue.append((nx, ny, path + [move_name]))

        if tail_path and len(tail_path) > 0:
            first_move = tail_path[0]
            LAST_MOVES[game_id] = first_move
            return first_move

    # 4. Desempate final: Priorizar la casilla con mayor área libre, salidas y penalizar colisiones o bordes
    best_move = valid_moves[0][2]
    best_score = -999999

    for dx, dy, move_name, pos in valid_moves:
        space, open_exits = count_escape_corridors(
            pos, obstacles, width, height)
        border_penalty = 0
        if pos[0] == 0 or pos[0] == width - 1 or pos[1] == 0 or pos[1] == height - 1:
            border_penalty = 2

        head_danger_penalty = 0
        if (pos in opp_next_moves) and (snake_len <= opp_len):
            head_danger_penalty = 50

        choke_penalty = 0
        if open_exits <= 1 or space < snake_len * 2:
            choke_penalty = 80

        score = (space * 10) + (open_exits * 5) - border_penalty - \
            head_danger_penalty - choke_penalty
        if score > best_score:
            best_score = score
            best_move = move_name

    LAST_MOVES[game_id] = best_move
    return best_move


def get_safe_snake_direction(data, snake_info=None):
    """Auxiliar mantenido para compatibilidad."""
    board = data.get('board', '')
    side = data.get('side', 'A')
    return choose_smart_snake_direction(board, side)


async def process_wall(websocket, request_data):
    data = request_data.get('data', {})
    safe_row = clamp_non_negative(randint(0, 8), min_val=0, max_val=8)
    safe_col = clamp_non_negative(randint(0, 8), min_val=0, max_val=8)

    await send(
        websocket,
        'wall',
        {
            'game_id': data.get('game_id', ''),
            'turn_token': data.get('turn_token', ''),
            'row': safe_row,
            'col': safe_col,
            'orientation': 'h' if randint(0, 1) == 0 else 'v'
        },
    )


if __name__ == '__main__':
    if len(sys.argv) >= 2:
        auth_token = sys.argv[1]
        asyncio.get_event_loop().run_until_complete(start(auth_token))
    else:
        print('please provide your auth_token')
