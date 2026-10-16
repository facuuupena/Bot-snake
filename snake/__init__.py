"""
Módulo principal del Bot Snake.
Arquitectura modularizada para mayor claridad, escalabilidad y mantenimiento.
"""
from snake.constants import (
    BLOCKED_OPPONENTS,
    OPPOSITE_MOVES,
    HISTORY,
    OPENED_GAMES,
    LOGS_DIR,
    LAST_MOVES,
    GAME_ACTIVE_TARGET,
    GAME_TARGET_DIGITS,
    # v8: Bombas de proximidad
    GAME_TURN_COUNTER,
    BOMB_LARGE,
    BOMB_SMALL,
    BOMB_LARGE_RADIUS,
    BOMB_SMALL_RADIUS,
    BOMB_DISABLE_ROUND,
)
from snake.geometry import (
    clamp_non_negative,
    sanitize_columns,
    flood_fill_count,
    count_escape_corridors,
)
from snake.parser import parse_official_snake_board
from snake.strategy import (
    choose_smart_snake_direction,
    get_safe_snake_direction,
)
from snake.visualizer import (
    LIVE_CLIENTS,
    broadcast_live_event,
    start_live_server,
)
from snake.network import (
    send,
    log_event,
    log_action,
    write_game_log,
    process_wall,
    process_move,
    process_your_turn,
    play,
    start,
)
