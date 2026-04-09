import asyncio
import json
import websockets

async def test_websocket():
    uri = "ws://localhost:8765"
    print(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as ws:
            print("Connected! Sending query...")
            payload = {"query": "Hello JARVIS! This is a test.", "mode": "local"}
            await ws.send(json.dumps(payload))
            
            # Listen for responses (status_update, jarvis_reply, tool info, etc.)
            while True:
                try:
                    response = await ws.recv()
                    data = json.loads(response)
                    print(f"\nReceived Event [{data.get('event')}]:\n{json.dumps(data, indent=2)}")
                    
                    if data.get("event") == "jarvis_reply" or data.get("recoverable") is False:
                        break
                except websockets.exceptions.ConnectionClosed:
                    print("Connection closed by server.")
                    break
    except ConnectionRefusedError:
        print(f"Connection refused. Make sure the server is running on {uri}")

if __name__ == "__main__":
    asyncio.run(test_websocket())
