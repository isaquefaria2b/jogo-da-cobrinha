import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


APP_DIR = Path(__file__).resolve().parent
PLAYERS_FILE = APP_DIR / "jogadores.txt"
MAX_NAME_LENGTH = 24
MAX_REQUEST_BYTES = 2048
PLAYERS_LOCK = threading.Lock()
PORT = int(os.environ.get("PORT", "8000"))


class GameRequestHandler(BaseHTTPRequestHandler):
    def send_bytes(self, status, content_type, body, download_name=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if download_name:
            self.send_header(
                "Content-Disposition", f'attachment; filename="{download_name}"'
            )
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_bytes(status, "application/json; charset=utf-8", body)

    def read_player_names(self):
        if not PLAYERS_FILE.exists():
            return []
        return [
            line.strip()
            for line in PLAYERS_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def do_GET(self):
        path = urlsplit(self.path).path

        if path == "/":
            path = "/index.html"

        if path == "/index.html":
            try:
                body = (APP_DIR / "index.html").read_bytes()
            except OSError as error:
                self.log_error("Não foi possível abrir index.html: %s", error)
                self.send_json(500, {"error": "Não foi possível abrir o jogo."})
                return
            self.send_bytes(200, "text/html; charset=utf-8", body)
            return

        if path == "/api/players":
            try:
                with PLAYERS_LOCK:
                    names = self.read_player_names()
            except OSError as error:
                self.log_error("Não foi possível ler jogadores.txt: %s", error)
                self.send_json(500, {"error": "Não foi possível ler a lista de jogadores."})
                return
            self.send_json(200, {"count": len(names), "names": names})
            return

        if path == "/jogadores.txt":
            try:
                with PLAYERS_LOCK:
                    body = PLAYERS_FILE.read_bytes() if PLAYERS_FILE.exists() else b""
            except OSError as error:
                self.log_error("Não foi possível ler jogadores.txt: %s", error)
                self.send_json(500, {"error": "Não foi possível baixar a lista de jogadores."})
                return
            self.send_bytes(
                200,
                "text/plain; charset=utf-8",
                body,
                download_name="jogadores.txt",
            )
            return

        self.send_json(404, {"error": "Endereço não encontrado."})

    def do_POST(self):
        if urlsplit(self.path).path != "/api/players":
            self.send_json(404, {"error": "Endereço não encontrado."})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"error": "Tamanho da requisição inválido."})
            return

        if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
            self.send_json(413, {"error": "A requisição está vazia ou é grande demais."})
            return

        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {"error": "Envie um nome válido em formato JSON."})
            return

        if not isinstance(payload, dict) or not isinstance(payload.get("name"), str):
            self.send_json(400, {"error": "O nome do jogador é obrigatório."})
            return

        name = payload["name"].strip()
        if (
            not name
            or len(name) > MAX_NAME_LENGTH
            or len(name.splitlines()) != 1
            or any(ord(character) < 32 or ord(character) == 127 for character in name)
        ):
            self.send_json(
                400,
                {"error": "Use um nome de 1 a 24 caracteres, sem quebras de linha."},
            )
            return

        try:
            with PLAYERS_LOCK:
                with PLAYERS_FILE.open("a", encoding="utf-8", newline="\n") as file:
                    file.write(f"{name}\n")
                names = self.read_player_names()
        except OSError as error:
            self.log_error("Não foi possível salvar jogador em jogadores.txt: %s", error)
            self.send_json(500, {"error": "Não foi possível salvar o jogador no arquivo."})
            return

        self.send_json(201, {"count": len(names), "names": names})


def main():
    PLAYERS_FILE.touch(exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), GameRequestHandler)
    print(f"Jogo iniciado na porta {PORT}.")
    print("O arquivo jogadores.txt será atualizado a cada entrada.")
    print("Pressione Ctrl+C para encerrar o servidor.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
