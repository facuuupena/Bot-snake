"""
Constantes y estados globales compartidos del Bot.
"""

BLOCKED_OPPONENTS = {'jigglypuff', 'jiglypuf', 'jiggly'}

OPPOSITE_MOVES = {
    'up': 'down',
    'down': 'up',
    'left': 'right',
    'right': 'left'
}

# Historial de eventos por partida
HISTORY = {}
OPENED_GAMES = set()
LOGS_DIR = "logs"

# Memoria de estado táctico por partida
LAST_MOVES = {}
GAME_ACTIVE_TARGET = {}
GAME_TARGET_DIGITS = {}

# v8: Contador de turnos por partida para saber cuándo desaparecen las bombas (ronda 150)
GAME_TURN_COUNTER = {}

# v8: Caracteres de bomba (fuera del BMP - requieren iteración por code point)
BOMB_LARGE = '\U0001f4a3'   # 💣 zona 5×5 (Chebyshev ≤ 2)
BOMB_SMALL = '\U0001f9e8'   # 🧨 zona 3×3 (Chebyshev ≤ 1)
BOMB_LARGE_RADIUS = 2
BOMB_SMALL_RADIUS = 1
BOMB_DISABLE_ROUND = 150

