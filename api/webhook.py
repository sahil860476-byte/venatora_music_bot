import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            update = json.loads(self.rfile.read(length))

            message = update.get("message", {})
            chat_id = message.get("chat", {}).get("id")
            command = message.get("text", "").split()[0].lower()

            if not chat_id:
                self.respond()
                return

            if command == "/start":
                reply = "🎵 Welcome to VENATORA!\n\nUse /help to see commands."

            elif command == "/help":
                reply = "VENATORA Commands:\n/start\n/play\n/pause\n/resume\n/skip\n/stop\n/queue"

            elif command == "/play":
                reply = "Music streaming requires a separate voice-chat service. Vercel cannot run PyTgCalls."

            else:
                reply = "Unknown command. Send /help."

            token = os.environ["BOT_TOKEN"]
            url = f"https://api.telegram.org/bot{token}/sendMessage"

            data = json.dumps({
                "chat_id": chat_id,
                "text": reply
            }).encode()

            request = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json"}
            )

            urllib.request.urlopen(request, timeout=8)

        except Exception:
            pass

        self.respond()

    def respond(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_GET(self):
        self.respond()
