import asyncio
import websockets


async def test():
    uri = "ws://127.0.0.1:8000/ws/1/1"

    async with websockets.connect(uri) as websocket:
        print("Sandeep connected!")

        await websocket.send("Hi Amit!")

        while True:
            message = await websocket.recv()
            print("Amit:", message)


asyncio.run(test())