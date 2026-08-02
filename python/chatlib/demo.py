"""Demo da lib chatlib: mostra markdown, code blocks, comandos e replies.

Corre com:  bash run.sh
"""

import time

from textual.app import App, ComposeResult
from textual.containers import Container, ScrollableContainer
from textual.widgets import Input, Markdown, Static

from chatlib import ChatApp


class DemoChat(ChatApp):
    """ChatApp com um bot simulado que responde a comandos e mensagens."""

    def compose(self) -> ComposeResult:
        yield Container(
            ScrollableContainer(id="chat-log"),
            Input(placeholder="Escreve /help, /code, /reply <id> <texto>, ou uma mensagem…", id="input-line"),
        )

    def on_mount(self) -> None:
        super().on_mount()
        # Boas-vindas com markdown + code block
        self.receive_message(
            "Bem-vindo ao **chatlib**! 👋\n\n"
            "Podes enviar comandos:\n"
            "- `/help` — mostra esta ajuda\n"
            "- `/code` — mostra um exemplo com syntax highlighting\n\n"
            "Tudo o que escreveres aparece renderizado em Markdown."
        )

    def on_input_submitted(self, message: Input.Submitted) -> None:
        """Interceta comandos antes de os passar ao ChatApp."""
        del message
        inp = self.query_one("#input-line", Input)
        text = inp.value.strip()
        if not text:
            return
        inp.value = ""
        if text.startswith("/"):
            parts = text[1:].split(maxsplit=1)
            if not parts:
                return
            cmd = parts[0]
            args = parts[1] if len(parts) > 1 else ""
            if cmd == "reply":
                # /reply <msg_id> <text>
                reply_parts = args.split(maxsplit=1)
                if len(reply_parts) != 2:
                    self.receive_message("Uso: /reply <msg_id> <texto>")
                    return
                reply_id, reply_text = reply_parts
                mid = self.send_message(reply_text, reply_to=reply_id)
                self._fake_reply(mid, reply_text)
            else:
                self.send_command(text[1:].strip())
        else:
            mid = self.send_message(text)
            self._fake_reply(mid, text)
    def _handle_command(self, command: str) -> None:
        """Bot que responde a comandos conhecidos."""
        if command == "help":
            self.receive_message(
                "## Comandos disponíveis\n\n"
                "- `/help` — mostra esta ajuda\n"
                "- `/code` — mostra um bloco de código em Python\n"
                "- `/reply <id> <texto>` — responde a uma mensagem"
            )
        elif command == "code":
            self.receive_message(
                "Aqui tens um exemplo com **syntax highlighting**:\n\n"
                "```python\n"
                "def fib(n: int) -> int:\n"
                "    a, b = 0, 1\n"
                "    for _ in range(n):\n"
                "        a, b = b, a + b\n"
                "    return a\n"
                "```"
            )
        else:
            self.receive_message(f"Comando desconhecido: `/{command}`. Tenta `/help`.")

    def _fake_reply(self, msg_id: str, text: str) -> None:
        """Simula uma resposta do 'outro lado' à mensagem enviada."""
        time.sleep(0.6)
        self.receive_message(f"Recebido: _{text}_", reply_to=msg_id)


if __name__ == "__main__":
    DemoChat().run()
