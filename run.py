"""
Punto de entrada principal del Bot Snake.
Arquitectura modular: Este archivo coordina el arranque y re-exporta
todas las funciones y módulos para compatibilidad total con scripts y tests.
"""
import asyncio
from random import randint
import sys
import websockets

import snake
from snake.constants import (
    BLOCKED_OPPONENTS,
    GAME_ACTIVE_TARGET,
    GAME_TARGET_DIGITS,
    HISTORY,
    LOGS_DIR,
    OPENED_GAMES,
    OPPOSITE_MOVES,
    LAST_MOVES,
)
from snake.geometry import (
    clamp_non_negative,
    count_escape_corridors,
    flood_fill_count,
    sanitize_columns,
)
from snake.parser import (
    parse_official_snake_board,
)
from snake.strategy import (
    choose_smart_snake_direction,
    get_safe_snake_direction,
)
from snake.visualizer import (
    GUI_PROCESS,
    LIVE_CLIENTS,
    broadcast_live_event,
    ensure_gui_running,
    live_ws_handler,
    start_live_server,
)
import snake.network as _net

# Re-exportamos funciones de red sincronizando las referencias
log_event = _net.log_event
log_action = _net.log_action
write_game_log = _net.write_game_log
send = _net.send
start = _net.start
play = _net.play
process_your_turn = _net.process_your_turn
process_wall = _net.process_wall

process_move = _net.process_move

if __name__ == '__main__':
    if len(sys.argv) >= 2:
        auth_token = sys.argv[1]
        asyncio.get_event_loop().run_until_complete(start(auth_token))
    else:
        print('please provide your auth_token')
