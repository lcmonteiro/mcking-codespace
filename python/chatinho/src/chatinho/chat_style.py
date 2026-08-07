"""ChatStyle: programmatic style builder for chatinho.

Build the chat UI theme in Python instead of editing raw CSS:

    from chatinho import ChatApp, ChatStyle

    style = ChatStyle(accent="#ff5733", sent_bubble_bg="#1a4d3a")
    app = ChatApp(style=style)

Use ``dataclasses.replace`` to tweak a base style without touching the rest:

    from dataclasses import replace

    dark = ChatStyle()
    green = replace(dark, accent="#00ff88")
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ChatStyle:
    """Theme colours for the chat UI.

    Every field is a hex colour string; defaults reproduce the classic
    chatlib look. ``to_css()`` turns the values into a Textual stylesheet.
    """

    # Screen / layout
    screen_bg: str = "#0b141a"
    chat_bg: str = "#0b141a"

    # Scrollbar
    scrollbar_bg: str = "#1f2c33"
    scrollbar_color: str = "#8696a0"
    scrollbar_hover_bg: str = "#2a3942"
    scrollbar_hover_color: str = "#e9edef"

    # Input line
    input_bg: str = "#202c33"
    input_border: str = "#2a3942"
    input_color: str = "#e9edef"
    input_focus_border: str = "#00a884"

    # Accent (reply outline + quote border)
    accent: str = "#00a884"

    # Sent bubbles
    sent_bubble_bg: str = "#005c4b"
    sent_bubble_border: str = "#005c4b"
    sent_text: str = "#e9edef"
    sent_header: str = "#8fd6b4"

    # Received bubbles
    received_bubble_bg: str = "#202c33"
    received_bubble_border: str = "#202c33"
    received_text: str = "#e9edef"
    received_header: str = "#7de0a3"

    # Quote (reply preview)
    quote_color: str = "#8696a0"
    quote_bg: str = "#111b21"

    def to_css(self) -> str:
        """Render this style as a Textual CSS string."""
        s = self
        return f"""\
Screen {{
    layout: vertical;
    background: {s.screen_bg};
}}
#chat-log {{
    height: 1fr;
    overflow-y: auto;
    padding: 1 2;
    background: {s.chat_bg};
}}
.scrollbar {{
    background: {s.scrollbar_bg};
    color: {s.scrollbar_color};
}}
.scrollbar:hover {{
    background: {s.scrollbar_hover_bg};
    color: {s.scrollbar_hover_color};
}}
#input-line {{
    height: 3;
    dock: bottom;
    background: {s.input_bg};
    border: round {s.input_border};
    color: {s.input_color};
}}
#input-line:focus {{
    border: round {s.input_focus_border};
}}
.message-container {{
    layout: horizontal;
    width: 100%;
    padding: 0 0 1 0;
    height: auto;
}}
.message-container.reply-target .message-bubble {{
    outline: thick {s.accent};
}}
.message-container.sent {{
    align: right top;
}}
.message-container.received {{
    align: left top;
}}
.message-bubble {{
    layout: vertical;
    max-width: 90%;
    padding: 1 2;
    border: round {s.received_bubble_border};
    background: {s.received_bubble_bg};
    color: {s.received_text};
    height: auto;
}}
.message-container.sent .message-bubble {{
    background: {s.sent_bubble_bg};
    border: round {s.sent_bubble_border};
    color: {s.sent_text};
}}
.message-container.received .message-bubble {{
    background: {s.received_bubble_bg};
    border: round {s.received_bubble_border};
    color: {s.received_text};
}}
.message-header {{
    color: {s.received_header};
    text-style: bold;
    margin: 0;
}}
.message-container.sent .message-header {{
    color: {s.sent_header};
}}
.message-body {{
    margin: 0;
}}
.message-quote {{
    color: {s.quote_color};
    background: {s.quote_bg};
    border-left: thick {s.accent};
    padding: 0 1;
    margin: 0 0 1 0;
}}
"""
