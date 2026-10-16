"""
Parseador del tablero oficial del juego Snake (v1 a v8).
Convierte la representación de texto en estructuras de datos con posiciones y obstáculos.
Soporte v8: detecta bombas 💣 (gran, zona 5×5) y 🧨 (chica, zona 3×3) y calcula
las celdas de peligro de explosión mediante distancia Chebyshev.
"""
from snake.constants import (
    GAME_ACTIVE_TARGET,
    GAME_TARGET_DIGITS,
    BOMB_LARGE,
    BOMB_SMALL,
    BOMB_LARGE_RADIUS,
    BOMB_SMALL_RADIUS,
    BOMB_DISABLE_ROUND,
    GAME_TURN_COUNTER,
)


def parse_official_snake_board(board_str, my_side='A', board_size=None, game_id=None):
    """
    Parsea el tablero oficial del juego (con soporte para versiones 1 a 7):
    - 'A': Cabeza de la serpiente A.
    - 'a': Cuerpo de la serpiente A.
    - 'B': Cabeza de la serpiente B.
    - 'b': Cuerpo de la serpiente B.
    - 'Ⓐ' / 'Ⓑ': Comida de cola tras colapso (v7).
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
        return {
            'head': (0, 0),
            'body': [],
            'tail': (0, 0),
            'opp_head': None,
            'opp_body': [],
            'obstacles': set(),
            'apples': [(5, 5)],
            'multipliers': [],
            'bad_digits': set(),
            'width': width,
            'height': height,
        }

    lines = [line.strip() for line in board_str.splitlines() if line.strip()]
    if not lines:
        return {
            'head': (0, 0),
            'body': [],
            'tail': (0, 0),
            'opp_head': None,
            'opp_body': [],
            'obstacles': set(),
            'apples': [(5, 5)],
            'multipliers': [],
            'bad_digits': set(),
            'width': width,
            'height': height,
        }

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
    digits_found = {}  # {digit_int: [(x, y), ...]}

    # v7: Comida de cola colapsada (Ⓐ o Ⓑ)
    opp_tail_food_set = {'Ⓐ', '\u24b6'} if my_head_char == 'A' else {'Ⓑ', '\u24b7'}
    own_deny_food_set = {'Ⓑ', '\u24b7'} if my_head_char == 'A' else {'Ⓐ', '\u24b6'}
    opp_tail_food = []
    own_deny_food = []

    # v8: Bombas de proximidad
    bombs_large = []   # 💣 zona Chebyshev ≤ 2 (5×5)
    bombs_small = []   # 🧨 zona Chebyshev ≤ 1 (3×3)

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
            elif char in opp_tail_food_set:
                opp_tail_food.append((x, y))
            elif char in own_deny_food_set:
                own_deny_food.append((x, y))
            elif char.isdigit() and char != '0':
                digit_val = int(char)
                digits_found.setdefault(digit_val, []).append((x, y))
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
            elif char == BOMB_LARGE:
                bombs_large.append((x, y))   # v8: 💣 bomba grande
            elif char == BOMB_SMALL:
                bombs_small.append((x, y))   # v8: 🧨 bomba chica

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
        for digit_val, positions in digits_found.items():
            if digit_val == target_digit:
                target_apples.extend(positions)
            else:
                for pos in positions:
                    bad_digits.add(pos)
                    obstacles.add(pos)  # Dígitos incorrectos en la secuencia actúan como obstáculos mortales (-500 pts)

    # v7+: Prioridad estricta de objetivos:
    # 1. Comida de cola rival (Ⓐ/Ⓑ) -> +100 pts x multiplicador + crecimiento
    # 2. Si el dígito es bajo (1 o 2): evitarlo / despriorizarlo frente a Multiplicadores 'X' y manzanas normales '*'
    # 3. Si el dígito es >= 3: alta prioridad en la secuencia
    if target_digit in (1, 2):
        all_targets = opp_tail_food + multipliers + apples + target_apples + own_deny_food
    else:
        all_targets = opp_tail_food + target_apples + multipliers + apples + own_deny_food

    if head_pos is None:
        head_pos = (0, 0)
    if not all_targets:
        all_targets = [(min(5, width - 1), min(5, height - 1))]

    tail_pos = my_body[-1] if my_body else head_pos

    # v8: Calcular celdas de peligro de explosión (Chebyshev)
    # Solo mientras no hayan pasado BOMB_DISABLE_ROUND turnos (ronda 150)
    bomb_danger_cells = set()
    turn = GAME_TURN_COUNTER.get(game_id, 0) if game_id else 0
    if turn < BOMB_DISABLE_ROUND:
        for bx, by in bombs_large:
            for dx in range(-BOMB_LARGE_RADIUS, BOMB_LARGE_RADIUS + 1):
                for dy in range(-BOMB_LARGE_RADIUS, BOMB_LARGE_RADIUS + 1):
                    bomb_danger_cells.add((bx + dx, by + dy))
        for bx, by in bombs_small:
            for dx in range(-BOMB_SMALL_RADIUS, BOMB_SMALL_RADIUS + 1):
                for dy in range(-BOMB_SMALL_RADIUS, BOMB_SMALL_RADIUS + 1):
                    bomb_danger_cells.add((bx + dx, by + dy))

    return {
        'head': head_pos,
        'body': my_body,
        'tail': tail_pos,
        'opp_head': opp_head,
        'opp_body': opp_body,
        'obstacles': obstacles,
        'apples': all_targets,
        'target_pos': opp_tail_food[0] if opp_tail_food else (target_apples[0] if target_apples else None),
        'opp_tail_food': opp_tail_food,
        'own_deny_food': own_deny_food,
        'multipliers': multipliers,
        'bad_digits': bad_digits,
        'target_digit': target_digit,
        'width': max(1, width),
        'height': max(1, height),
        # v8: Bombas de proximidad
        'bombs_large': bombs_large,
        'bombs_small': bombs_small,
        'bomb_danger_cells': bomb_danger_cells,
    }
