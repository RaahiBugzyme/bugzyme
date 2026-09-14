import asyncio
import websockets
import json


async def main():
    url = "ws://127.0.0.1:8000/ws/1?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.59rKU5nT26Eew37xt6Tk86L7S3v5j1x1AvIf8cmVLbo"

    async with websockets.connect(url) as websocket:
        print("Connected!")

        async def send_messages():
            while True:
                message = await asyncio.to_thread(input, "You: ")

                if message == "/typing":
                    await websocket.send(json.dumps({
                        "type": "typing"
                    }))

                elif message.startswith("/read"):
                    message_id = int(message.split()[1])

                    await websocket.send(json.dumps({
                        "type": "read",
                        "message_id": message_id
                    }))

                else:
                    print("SENDING:", repr(message))

                    await websocket.send(json.dumps({
                        "type": "message",
                        "content": message
                    }))

        send_task = asyncio.create_task(send_messages())

        while True:
            message = await websocket.recv()
            print("Received:", message)


asyncio.run(main())


