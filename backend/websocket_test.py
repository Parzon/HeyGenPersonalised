import asyncio
import websockets

async def test_websocket():
    uri = "ws://0.0.0.0:8000/ws/conversation"
    async with websockets.connect(uri) as websocket:
        # Send a test message
        await websocket.send("Hello WebSocket server!")
        # Wait for the response
        response = await websocket.recv()
        print(response)

# Run the async function
if __name__ == "__main__":
    asyncio.run(test_websocket())
