import asyncio
import json
import os
import random
import sys
import time
import websockets

def randint(*args, **kwargs):
    if 'run' in sys.modules and hasattr(sys.modules['run'], 'randint'):
        return sys.modules['run'].randint(*args, **kwargs)
    return random.randint(*args, **kwargs)


from snake.constants import (
    BLOCKED_OPPONENTS,
    HISTORY,
    LOGS_DIR,
)
from snake.geometry import (
    clamp_non_negative,
    sanitize_columns,
)
from snake.strategy import (
    choose_smart_snake_direction,
)
from snake.visualizer import (
    broadcast_live_event,
    start_live_server,
)


def log_event(game_id, message):
    HISTORY.setdefault(game_id, []).append('< ' + json.dumps(message))


def log_action(game_id, message):
    HISTORY.setdefault(game_id, []).append('> ' + json.dumps(message))


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

            # Transmitir en tiempo real al visualizador de navegador y Tkinter
            await broadcast_live_event(request_data)

            if request_data['event'] == 'update_user_list':
                pass
            if request_data['event'] == 'game_over':
                game_id = request_data['data'].get('game_id')
                if game_id:
                    log_event(game_id, request_data)
                    write_game_log(game_id)
            if request_data['event'] == 'challenge':
                opponent = str(request_data.get('data', {}).get('opponent', '')).lower()
                if any(blocked in opponent for blocked in BLOCKED_OPPONENTS):
                    print(f"[BLOQUEADO] Desafío ignorado del usuario no autorizado: {opponent}")
                else:
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
    s1 = data.get('score_1', 0)
    s2 = data.get('score_2', 0)
    my_multiplier = m1 if side == 'A' else m2
    my_score = s1 if side == 'A' else s2
    opp_score = s2 if side == 'A' else s1

    snake_move = choose_smart_snake_direction(
        board, side, game_id=game_id, board_size=board_size, my_multiplier=my_multiplier, my_score=my_score, opp_score=opp_score)

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
