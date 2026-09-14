import asyncio
import websockets

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.59rKU5nT26Eew37xt6Tk86L7S3v5j1x1AvIf8cmVLbo"



async def main():
    url = f"ws://127.0.0.1:8000/ws/1?token={TOKEN}"

    async with websockets.connect(url) as websocket:
        print("Connected!")

        await websocket.send("Hello Rahul")

        while True:
            message = await websocket.recv()
            print("Received:", message)

asyncio.run(main())