import asyncio
import json

import websockets


async def websocket_smoke_test():
    uri = "ws://localhost:8765"
    print(f"Connecting to {uri}...")

    try:
        async with websockets.connect(uri) as ws:
            print("Connected! Sending query...")
            payload = {"event": "user_query", "query": "Hello JARVIS! This is a test.", "mode": "local"}
            await ws.send(json.dumps(payload))

            while True:
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=30)
                    data = json.loads(response)
                    print(f"\nReceived Event [{data.get('event')}]:\n{json.dumps(data, indent=2)}")

                    if data.get("event") == "jarvis_error" and data.get("recoverable") is False:
                        break
                    if data.get("event") == "jarvis_stream_chunk" and data.get("done"):
                        break
                except asyncio.TimeoutError:
                    print("Timed out waiting for a backend event.")
                    break
                except websockets.exceptions.ConnectionClosed:
                    print("Connection closed by server.")
                    break
    except ConnectionRefusedError:
        print(f"Connection refused. Make sure the server is running on {uri}")


if __name__ == "__main__":
    asyncio.run(websocket_smoke_test())
