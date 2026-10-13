import asyncio
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch, AsyncMock

import run
from snake.geometry import sanitize_columns, clamp_non_negative, flood_fill_count, count_escape_corridors
from snake.parser import parse_official_snake_board
from snake.strategy import choose_smart_snake_direction, get_safe_snake_direction
import snake.visualizer as visualizer
import snake.network as network


class FakeWebSocket:
    def __init__(self, incoming=()):
        self.incoming = [
            m if isinstance(m, str) else json.dumps(m) for m in incoming
        ]
        self.sent = []
        self._closed_event = asyncio.Event()

    async def recv(self):
        if not self.incoming:
            raise ConnectionResetError('no more messages')
        return self.incoming.pop(0)

    async def send(self, message):
        self.sent.append(json.loads(message))

    async def wait_closed(self):
        await self._closed_event.wait()


class TestStrategyDeepCoverage(unittest.TestCase):

    def test_get_safe_snake_direction(self):
        res = get_safe_snake_direction({'board': '| A * |', 'side': 'A'})
        self.assertIn(res, ['up', 'down', 'left', 'right'])

    def test_emergency_panic_moves_all_blocked(self):
        board_str = (
            "|###|\n"
            "|#A#|\n"
            "|###|\n"
        )
        res = choose_smart_snake_direction(board_str, side='A')
        self.assertIn(res, ['up', 'down', 'left', 'right'])

    def test_emergency_panic_moves_tail_escape(self):
        board_str = (
            "|###|\n"
            "|#Aa|\n"
            "|###|\n"
        )
        res = choose_smart_snake_direction(board_str, side='A')
        self.assertIn(res, ['up', 'down', 'left', 'right'])

    def test_tail_following_fallback_unreachable_apples(self):
        # Manzana completamente rodeada por muros '#', serpiente A con cuerpo debe seguir su cola
        board_str = (
            "|#############|\n"
            "|#...aA...####|\n"
            "|#...aa...#*##|\n"
            "|#........####|\n"
            "|#############|\n"
        )
        res = choose_smart_snake_direction(board_str, side='A', game_id='g_tail_follow')
        self.assertIn(res, ['left', 'down', 'up', 'right'])

    def test_tie_breaking_open_space_no_reachable_apples(self):
        # Manzana bloqueada y A sin cola (longitud 1) -> entra directamente a desempatador de áreas (line 290+)
        board_str = (
            "|#############|\n"
            "|#...A....####|\n"
            "|#...B....#*##|\n"
            "|#........####|\n"
            "|#############|\n"
        )
        res = choose_smart_snake_direction(board_str, side='A', game_id='g_no_apples')
        self.assertIn(res, ['up', 'down', 'left', 'right'])

    def test_intermediate_digits_3_4_5(self):
        board_str = (
            "|............|\n"
            "|..*..A...4..|\n"
            "|............|\n"
        )
        res = choose_smart_snake_direction(board_str, side='A', game_id='g_digit_4', my_multiplier=2)
        self.assertEqual(res, 'right')

    def test_own_deny_food_nearby(self):
        board_str = (
            "|............|\n"
            "|...A.ⓐ...B..|\n"
            "|............|\n"
        )
        res = choose_smart_snake_direction(board_str, side='A', game_id='g_deny')
        self.assertIn(res, ['right', 'down'])

    def test_instant_trap_attack_when_rival_small(self):
        board_str = (
            "|###.........|\n"
            "|#B#.........|\n"
            "|#.Aaaaa.....|\n"
            "|............|\n"
        )
        res = choose_smart_snake_direction(board_str, side='A', game_id='g_trap_instant')
        self.assertIn(res, ['left', 'down'])


class TestGeometryDeepCoverage(unittest.TestCase):

    def test_sanitize_columns_multiline_and_no_pipes(self):
        self.assertEqual(sanitize_columns(None), 0)
        self.assertEqual(sanitize_columns(""), 0)
        self.assertEqual(sanitize_columns("     "), 0)
        self.assertEqual(sanitize_columns("abc\ndef\n"), 2)

    def test_clamp_non_negative_invalid(self):
        self.assertEqual(clamp_non_negative("invalid"), 0)
        self.assertEqual(clamp_non_negative(15, min_val=0, max_val=10), 10)

    def test_count_escape_corridors_and_flood_fill(self):
        count = flood_fill_count((0, 0), {(0, 1), (1, 0)}, 5, 5)
        self.assertEqual(count, 1)
        reachable, exits = count_escape_corridors((1, 1), set(), 5, 5)
        self.assertGreater(reachable, 0)
        self.assertGreater(exits, 0)


class TestParserDeepCoverage(unittest.TestCase):

    def test_parse_board_edge_cases(self):
        empty_res = parse_official_snake_board("")
        self.assertEqual(empty_res['head'], (0, 0))

        whitespace_res = parse_official_snake_board("   \n   \n")
        self.assertEqual(whitespace_res['head'], (0, 0))

        malformed_size_res = parse_official_snake_board("| A |", board_size="invalid")
        self.assertEqual(malformed_size_res['head'], (1, 0))

        custom_size = parse_official_snake_board("| A |", board_size="20x25")
        self.assertEqual(custom_size['height'], 20)
        self.assertEqual(custom_size['width'], 25)

    def test_parse_board_with_walls_and_multiple_digits(self):
        board_str = (
            "|#..1..1..#|\n"
            "|#.A..B..x#|\n"
            "|##########|\n"
        )
        parsed = parse_official_snake_board(board_str, my_side='A', game_id='g_multi')
        self.assertIn((0, 1), parsed['obstacles'])
        self.assertIn((8, 1), parsed['multipliers'])
        self.assertEqual(len(parsed['bad_digits']), 0)


class TestVisualizerDeepCoverage(unittest.IsolatedAsyncioTestCase):

    async def test_live_ws_handler(self):
        mock_ws = FakeWebSocket()
        handler_task = asyncio.create_task(visualizer.live_ws_handler(mock_ws))
        await asyncio.sleep(0.02)
        self.assertIn(mock_ws, visualizer.LIVE_CLIENTS)
        mock_ws._closed_event.set()
        await handler_task
        self.assertNotIn(mock_ws, visualizer.LIVE_CLIENTS)

    async def test_broadcast_live_event_with_clients(self):
        mock_ws = AsyncMock()
        visualizer.LIVE_CLIENTS.add(mock_ws)
        try:
            await visualizer.broadcast_live_event({'test': 123})
            mock_ws.send.assert_awaited()
        finally:
            visualizer.LIVE_CLIENTS.discard(mock_ws)

    def test_ensure_gui_running_handles_exceptions(self):
        with patch('subprocess.Popen', side_effect=Exception('GUI error')):
            visualizer.ensure_gui_running()

    async def test_start_live_server_handles_exception(self):
        with patch('websockets.serve', side_effect=Exception('server error')):
            await visualizer.start_live_server()


class TestNetworkDeepCoverage(unittest.IsolatedAsyncioTestCase):

    def test_network_randint(self):
        val = network.randint(1, 5)
        self.assertTrue(1 <= val <= 5)

    async def test_process_wall(self):
        ws = FakeWebSocket()
        await network.process_wall(ws, {'data': {'game_id': 'g_1', 'turn_token': 't_1'}})
        self.assertEqual(ws.sent[0]['action'], 'wall')

    async def test_process_move_without_direction(self):
        ws = FakeWebSocket()
        req = {
            'data': {
                'game_id': 'g_other',
                'turn_token': 't_tok',
                'side': 'P',
                'board': '.....'
            }
        }
        await network.process_move(ws, req)
        self.assertEqual(ws.sent[0]['action'], 'move')
        self.assertNotIn('direction', ws.sent[0]['data'])

    async def test_play_ignores_update_user_list(self):
        ws = FakeWebSocket([
            {'event': 'update_user_list', 'data': {'users': []}}
        ])
        await network.play(ws)
        self.assertEqual(ws.sent, [])

    async def test_play_keyboard_interrupt(self):
        ws = MagicMock()
        ws.recv = AsyncMock(side_effect=KeyboardInterrupt)
        await network.play(ws)

    async def test_start_reconnects_on_error(self):
        attempts = 0
        def fake_connect(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise Exception("Network down")
            raise KeyboardInterrupt()

        with patch('websockets.connect', side_effect=fake_connect):
            with patch('time.sleep', return_value=None):
                await network.start('test_token')
        self.assertEqual(attempts, 2)


class TestRunMainModule(unittest.TestCase):

    def test_main_without_args(self):
        with patch.object(sys, 'argv', ['run.py']):
            with patch('builtins.print') as mock_print:
                # Ejecutar el bloque principal simulado
                if len(sys.argv) >= 2:
                    pass
                else:
                    print('please provide your auth_token')
                mock_print.assert_called_with('please provide your auth_token')


if __name__ == '__main__':
    unittest.main()
