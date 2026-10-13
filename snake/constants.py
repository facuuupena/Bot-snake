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
