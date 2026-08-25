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


def write_game_log(game_id):
    try:
        with open(f"game_{game_id}.log", "w") as f:
            f.write("\n".join(HISTORY.get(game_id, [])) + "\n")
        print(f"saved game_{game_id}.log")
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


async def broadcast_live_event(message_data):
    if not LIVE_CLIENTS:
        return
    msg = json.dumps(message_data)
    for client in list(LIVE_CLIENTS):
        try:
            await client.send(msg)
        except Exception:
            LIVE_CLIENTS.discard(client)


async def start_live_server():
    try:
        async with websockets.serve(live_ws_handler, "localhost", 8765):
            print("🟢 Visualizador en vivo activo en ws://localhost:8765")
            visualizer_path = os.path.abspath("visualizer.html")
            if os.path.exists(visualizer_path):
                webbrowser.open(f"file://{visualizer_path}")
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
    snake_move = choose_smart_snake_direction(board, side, game_id=game_id)

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


def parse_official_snake_board(board_str, my_side='A'):
    """
    Parsea la cuadrícula oficial de 15x15 del tablero de Snake de The Code Challenge:
    - 'A' / 'B': Cabezas de las serpientes.
    - 'a' / 'b': Cuerpos de las serpientes.
    - '*': Comida (manzana).
    - ' ': Espacio libre.
    - '|': Bordes laterales del tablero.
    """
    if not isinstance(board_str, str) or not board_str:
        return {'head': (0, 0), 'body': [], 'tail': (0, 0), 'opp_head': None, 'opp_body': [], 'obstacles': set(), 'apples': [(5, 5)], 'width': 15, 'height': 15}

    lines = [line.strip() for line in board_str.splitlines() if line.strip()]
    if not lines:
        return {'head': (0, 0), 'body': [], 'tail': (0, 0), 'opp_head': None, 'opp_body': [], 'obstacles': set(), 'apples': [(5, 5)], 'width': 15, 'height': 15}

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

    height = len(lines)
    width = 0

    for y, raw_line in enumerate(lines):
        clean_line = raw_line
        if clean_line.startswith('|'):
            clean_line = clean_line[1:]
        if clean_line.endswith('|'):
            clean_line = clean_line[:-1]

        width = max(width, len(clean_line))

        for x, char in enumerate(clean_line):
            if char == '*':
                apples.append((x, y))
            elif char == my_head_char:
                head_pos = (x, y)
            elif char == my_body_char:
                my_body.append((x, y))
                obstacles.add((x, y))
            elif char == opp_head_char:
                opp_head = (x, y)
                obstacles.add((x, y))
            elif char in (opp_body_char, '#'):
                opp_body.append((x, y))
                obstacles.add((x, y))

    if head_pos is None:
        head_pos = (0, 0)
    if not apples:
        apples = [(5, 5)]

    tail_pos = my_body[-1] if my_body else head_pos

    return {
        'head': head_pos,
        'body': my_body,
        'tail': tail_pos,
        'opp_head': opp_head,
        'opp_body': opp_body,
        'obstacles': obstacles,
        'apples': apples,
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
    open_exits = sum(1 for rx, ry in reachables if 1 <= rx < width - 1 and 1 <= ry < height - 1)
    return len(reachables), open_exits


def choose_smart_snake_direction(board_str, side='A', game_id=None):
    """
    Algoritmo de Inteligencia Artificial Avanzada Dual (Ofensivo y Defensivo):
    1. Prevención estricta de giros de 180° sobre su propio cuello.
    2. Detección Defensiva de Encierro y Zonas de Estrangulamiento (Choke Points).
    3. Estrategia Ofensiva de Estrangulamiento: Si movernos a una posición recorta el espacio rival < su longitud, realiza el ATAQUE DE ENCIERRO.
    4. Evita colisiones de cabeza vulnerables con el rival a menos que seamos más largos.
    5. Modo Supervivencia Seguimiento de Cola (Tail-Following) si la manzana es peligrosa.
    6. Respaldo por Desesperación Inteligente (Smart Panic Tail Escape) si no hay casillas vacías.
    """
    parsed = parse_official_snake_board(board_str, side)
    head_x, head_y = parsed['head']
    my_body = parsed['body']
    tail_pos = parsed['tail']
    opp_head = parsed['opp_head']
    opp_body = parsed['opp_body']
    obstacles = parsed['obstacles']
    apples = parsed['apples']
    width = parsed['width']
    height = parsed['height']

    snake_len = len(my_body) + 1
    opp_len = len(opp_body) + 1
    last_move = LAST_MOVES.get(game_id)
    opposite = OPPOSITE_MOVES.get(last_move)

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
        # 1. Buscar si alguna casilla contigua corresponde a la PUNTA DE NUESTRA COLA (tail_pos)
        # La cola se moverá hacia adelante en este turno, liberando la casilla.
        for dx, dy, move_name in moves:
            if move_name == opposite:
                continue
            nx, ny = head_x + dx, head_y + dy
            if (nx, ny) == tail_pos:
                LAST_MOVES[game_id] = move_name
                return move_name

        # 2. Si la cola no está al lado, elegir cualquier casilla dentro del tablero evitando salirse
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
    # Si podemos movernos a una casilla que asfixia al rival encerrándolo en un bolsillo sin salida
    best_trap_move = None
    if opp_head and snake_len >= opp_len:
        for dx, dy, move_name, pos in valid_moves:
            sim_obstacles = set(obstacles) | {pos}
            opp_space = flood_fill_count(opp_head, sim_obstacles, width, height)
            my_space = flood_fill_count(pos, sim_obstacles, width, height)

            if opp_space < opp_len and my_space >= snake_len:
                best_trap_move = move_name
                break

    if best_trap_move:
        LAST_MOVES[game_id] = best_trap_move
        return best_trap_move

    # 2. Probar ruta BFS hacia la manzana más cercana con verificación Defensiva de Encierro y Corredores
    best_apple_path = None
    min_dist = 999999
    for a in apples:
        d = abs(head_x - a[0]) + abs(head_y - a[1])
        if d < min_dist:
            path = bfs_find_path((head_x, head_y), a)
            if path:
                min_dist = d
                best_apple_path = path

    if best_apple_path:
        first_move = best_apple_path[0]
        for dx, dy, move_name, pos in valid_moves:
            if move_name == first_move:
                space, open_exits = count_escape_corridors(pos, obstacles, width, height)
                is_head_danger = (pos in opp_next_moves) and (snake_len <= opp_len)
                is_choke = (open_exits <= 1 and space < snake_len * 1.5)
                if space >= min(snake_len + 2, 15) and not is_head_danger and not is_choke:
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
        space, open_exits = count_escape_corridors(pos, obstacles, width, height)
        border_penalty = 0
        if pos[0] == 0 or pos[0] == width - 1 or pos[1] == 0 or pos[1] == height - 1:
            border_penalty = 2

        head_danger_penalty = 0
        if (pos in opp_next_moves) and (snake_len <= opp_len):
            head_danger_penalty = 50

        choke_penalty = 0
        if open_exits <= 1 and space < snake_len * 1.5:
            choke_penalty = 40

        score = (space * 10) + (open_exits * 5) - border_penalty - head_danger_penalty - choke_penalty
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
