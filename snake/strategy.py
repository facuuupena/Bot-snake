"""
Motor de inteligencia artificial y toma de decisiones para Snake.
Implementa el algoritmo dual avanzado (ofensivo/defensivo) con BFS, Flood Fill,
ataque de estrangulamiento/encierro, fases de multiplicadores y seguimiento de cola.
v8: Evasión de bombas de proximidad 💣/🧨 mediante penalización de zona de peligro.
"""
from collections import deque
from snake.constants import LAST_MOVES, OPPOSITE_MOVES
from snake.geometry import flood_fill_count, count_escape_corridors
from snake.parser import parse_official_snake_board


def choose_smart_snake_direction(board_str, side='A', game_id=None, board_size=None, my_multiplier=1, my_score=0, opp_score=0):
    """
    Algoritmo de Inteligencia Artificial Avanzada Dual v8 (Ofensivo y Defensivo):
    1. Prevención estricta de giros de 180° sobre su propio cuello y evitación de choques.
    2. Caza Prioritaria de Cola Rival Colapsada (Ⓐ/Ⓑ) -> +100 pts x multiplicador por casilla (Modo Buitre Blitz).
    3. Detección Defensiva de Encierro y Zonas de Estrangulamiento (Choke Points).
    4. Estrategia Ofensiva de Estrangulamiento: Si movernos a una posición recorta el espacio rival < su longitud, realiza el ATAQUE DE ENCIERRO.
    5. Estrategia en Fases:
       - FASE 1 (Multiplicador < 5): Caza agresiva de 'X' para elevar ganancia temprana.
       - FASE 2 (Multiplicador >= 5): Caza voraz de cola rival y dígitos en secuencia (1..9), y comer 'X' de paso si está cerca.
    6. Denegación de Cola Propia (Deny): Pisarla si el rival está cerca para destruirla y evitar que sume puntos gratis.
    7. Modo Supervivencia Seguimiento de Cola (Tail-Following) si el área es peligrosa.
    8. v8: Evasión de bombas de proximidad 💣/🧨 — filtrado estricto de celdas peligrosas cuando hay alternativas seguras,
       penalización de -500 en desempate final si todas las opciones son zonas de bomba.
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
    opp_tail_food_set = set(parsed.get('opp_tail_food', []))
    own_deny_food_set = set(parsed.get('own_deny_food', []))
    width = parsed['width']
    height = parsed['height']
    # v8: Celdas de peligro de bomba (Chebyshev ≤ radio)
    bomb_danger_cells = parsed.get('bomb_danger_cells', set())

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

    # v8: Filtrado de bombas — si hay movimientos fuera de zona de peligro, descartar los que están dentro
    if bomb_danger_cells:
        safe_moves = [(dx, dy, mn, pos) for dx, dy, mn, pos in valid_moves if pos not in bomb_danger_cells]
        if safe_moves:
            valid_moves = safe_moves
        # Si TODOS los movimientos están en zona de bomba, se conservan todos (elegir el menos malo al final)

    # Identificar movimientos probables de la cabeza rival para no regalarnos
    opp_next_moves = set()
    if opp_head:
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            ox, oy = opp_head[0] + dx, opp_head[1] + dy
            if 0 <= ox < width and 0 <= oy < height and (ox, oy) not in obstacles:
                opp_next_moves.add((ox, oy))

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

    # 1. ATAQUE OFENSIVO DE ENCIERRO (Trap Attack Instantáneo):
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

    # 1.1 ATAQUE DE ESTRANGULAMIENTO / ENCIERRO ACTIVO (Constriction Attack):
    # Si la serpiente es grande (snake_len >= 6 y snake_len >= opp_len), priorizar encerrar y sofocar al rival
    best_constrict_move = None
    if opp_head and snake_len >= 6 and snake_len >= opp_len:
        cand_constrict = []
        for dx, dy, move_name, pos in valid_moves:
            if (pos in opp_next_moves) and (snake_len <= opp_len):
                continue
            sim_obstacles = set(obstacles) | {pos}
            opp_space = flood_fill_count(opp_head, sim_obstacles, width, height)
            my_space = flood_fill_count(pos, sim_obstacles, width, height)

            # Mantener espacio seguro para nosotros para no auto-encerrarnos
            if my_space >= min(snake_len + 3, 18):
                cand_constrict.append((opp_space, my_space, move_name))

        if cand_constrict:
            cand_constrict.sort(key=lambda x: (x[0], -x[1]))
            best_opp_space, best_my_space, top_move = cand_constrict[0]
            worst_opp_space = cand_constrict[-1][0]
            if best_opp_space <= max(opp_len * 3, 20) or (best_opp_space <= worst_opp_space - 6):
                best_constrict_move = top_move

    if best_constrict_move:
        LAST_MOVES[game_id] = best_constrict_move
        return best_constrict_move

    target_pos = parsed.get('target_pos')
    target_digit = parsed.get('target_digit')

    # Estrategia Dinámica Dual por Fases de Multiplicador:
    # FASE 1 (my_multiplier < 5): Crecimiento inicial -> Priorizar multiplicadores 'X' para alcanzar x5 rápidamente.
    # FASE 2 (my_multiplier >= 5): Voracidad de Secuencia -> Priorizar MÁXIMAMENTE todos los dígitos (1 al 9), especialmente altos (6..9).
    is_phase_1 = (my_multiplier < 5)

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
        is_opp_tail = (a in opp_tail_food_set)
        is_own_deny = (a in own_deny_food_set)

        race_penalty = 0
        target_bonus = 0
        multiplier_bonus = 0
        opp_tail_bonus = 0
        own_deny_bonus = 0

        if is_opp_tail:
            # v7: Modo Buitre Blitz - Comida de cola rival tras colapso (+100 pts x multiplicador + crecimiento)
            # ALTA PRIORIDAD DE CAZA ABSOLUTA
            opp_tail_bonus = 120
            if my_d <= 10:
                opp_tail_bonus = 150
            if opp_head and opp_d < my_d:
                race_penalty = 5
        elif is_own_deny:
            # v7: Denegación de cola propia colapsada (si el rival está cerca y estamos a <= 4 pasos, pisarla para borrarla)
            if opp_head and my_d <= 4:
                own_deny_bonus = 35
        elif is_target_digit:
            if target_digit in (1, 2):
                # Evitar tomar los puntos 1 y 2 para no perder turnos por puntos insignificantes.
                # Penalización (-35). Solo se toma si estamos directamente adyacentes (my_d <= 1) de paso.
                if my_d <= 1:
                    target_bonus = 5
                else:
                    target_bonus = -35
                race_penalty = 0
            elif target_digit in (6, 7, 8, 9):
                # ALTA PRIORIDAD POTENCIADA a dígitos altos (6, 7, 8, 9)
                # Si tenemos multiplicador activo (my_multiplier >= 2), ¡combo devastador para no ignorarlos jamás!
                target_bonus = 85
                if my_d <= 8:
                    target_bonus = 110
                if my_multiplier >= 2:
                    target_bonus += 35 + (my_multiplier * 5)
                if opp_head and opp_d < my_d:
                    race_penalty = 8
            else:
                # Dígitos intermedios (3, 4, 5)
                target_bonus = 45
                if my_d <= 8:
                    target_bonus = 60
                if my_multiplier >= 2:
                    target_bonus += 15
                if opp_head and opp_d < my_d:
                    race_penalty = 15

        elif a in multipliers_set:
            if is_phase_1 or (target_digit in (1, 2)):
                # Fase 1 (< x5) o cuando el target actual es 1 o 2:
                # Caza ultragresiva de 'X' para elevar multiplicador
                multiplier_bonus = 45
                if my_d <= 6:
                    multiplier_bonus = 65
            else:
                # Fase 2 (>= x5) con target >= 3:
                # Solo comer 'X' si está de paso o muy cerca (my_d <= 4)
                if my_d <= 4:
                    multiplier_bonus = 25
                else:
                    multiplier_bonus = 10

            if opp_head and opp_d < my_d:
                race_penalty = 8

        effective_dist = my_d + race_penalty - target_bonus - multiplier_bonus - opp_tail_bonus - own_deny_bonus
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

    # 3. Modo Supervivencia Defensivo: Intentar seguir la propia cola (Tail-Following) de forma 100% segura
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
            # Verificar que el primer movimiento hacia la cola no sea una colisión frontal suicida
            for dx, dy, move_name, pos in valid_moves:
                if move_name == first_move:
                    is_head_danger = (pos in opp_next_moves) and (snake_len <= opp_len)
                    if not is_head_danger:
                        LAST_MOVES[game_id] = first_move
                        return first_move

    # 4. Desempate final: Priorizar la casilla con mayor área libre, salidas abiertas y evitar esquinas atascadas
    best_move = valid_moves[0][2]
    best_score = -999999

    for dx, dy, move_name, pos in valid_moves:
        space, open_exits = count_escape_corridors(
            pos, obstacles, width, height)
        border_penalty = 0
        if pos[0] == 0 or pos[0] == width - 1 or pos[1] == 0 or pos[1] == height - 1:
            border_penalty = 5

        head_danger_penalty = 0
        if (pos in opp_next_moves) and (snake_len <= opp_len):
            head_danger_penalty = 100

        choke_penalty = 0
        if open_exits == 0:
            choke_penalty = 300
        elif open_exits == 1 or space < snake_len * 2:
            choke_penalty = 120

        constrict_bonus = 0
        if opp_head and snake_len >= 6 and snake_len >= opp_len:
            sim_obstacles = set(obstacles) | {pos}
            opp_space = flood_fill_count(opp_head, sim_obstacles, width, height)
            constrict_bonus = max(0, 30 - opp_space) * 8

        # v8: Penalización por zona de bomba (sólo llega aquí si TODOS los movimientos son zonas de bomba)
        bomb_penalty = 500 if pos in bomb_danger_cells else 0

        score = (space * 15) + (open_exits * 10) + constrict_bonus - border_penalty - \
            head_danger_penalty - choke_penalty - bomb_penalty
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
