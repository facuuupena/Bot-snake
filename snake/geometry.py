"""
Cálculos geométricos, validación de coordenadas y algoritmos de espacio (Flood Fill y corredores de escape).
"""
from collections import deque


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


def flood_fill_count(start_pos, obstacles, width, height, max_depth=60):
    """
    Algoritmo Flood-Fill BFS para calcular casillas accesibles.
    Previene meterse en callejones sin salida donde la serpiente se queda atrapada.
    """
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
