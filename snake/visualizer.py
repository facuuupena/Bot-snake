import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import websockets

LIVE_CLIENTS = set()
GUI_PROCESS = None


async def live_ws_handler(websocket):
    LIVE_CLIENTS.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        LIVE_CLIENTS.discard(websocket)


def ensure_gui_running():
    """Reabre automáticamente el visualizador Tkinter si el usuario lo cerró sin querer."""
    global GUI_PROCESS
    gui_script = os.path.abspath("gui_visualizer.py")
    if os.path.exists(gui_script) and (GUI_PROCESS is None or GUI_PROCESS.poll() is not None):
        try:
            GUI_PROCESS = subprocess.Popen([sys.executable, gui_script])
            print("[GUI] Visualizador Nativo de Escritorio Tkinter iniciado / reabierto")
            time.sleep(0.3)
        except Exception as e:
            print(f"Nota Visualizador Nativo: {e}")


async def broadcast_live_event(message_data):
    msg = json.dumps(message_data)

    # 1. Transmitir a visualizador web si hay clientes abiertos
    if LIVE_CLIENTS:
        for client in list(LIVE_CLIENTS):
            try:
                await client.send(msg)
            except Exception:
                LIVE_CLIENTS.discard(client)

    # 2. Transmitir a Visualizador Nativo de Escritorio Tkinter (localhost:8766)
    def send_to_gui():
        ensure_gui_running()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                s.connect(("localhost", 8766))
                s.sendall((msg + "\n").encode('utf-8'))
        except Exception:
            pass

    asyncio.get_event_loop().run_in_executor(None, send_to_gui)


async def start_live_server():
    ensure_gui_running()
    try:
        async with websockets.serve(live_ws_handler, "localhost", 8765):
            await asyncio.Future()  # mantener servidor abierto
    except Exception as e:
        print(f"Nota: Servidor de transmisión local: {e}")
