#!/usr/bin/env python3
"""
λ-tree — Symbolic Lambda Calculus Visualiser
=============================================

A terminal-friendly lambda calculus expression explorer.
Parse, reduce, and visualise λ-expressions as ASCII trees.

Features:
  - Parser: variables, abstractions, applications
  - β-reduction (normal order, call-by-name, call-by-value)
  - α-conversion (fresh variable generation)
  - Interactive mode: step through reductions
  - ASCII tree view of any expression
  - Church numeral encoding / decoding
  - Combinator library (S, K, I, Y, etc.)

Usage:
  python3 lambda_tree.py              # interactive REPL
  python3 lambda_tree.py --eval "(λx. x x) (λx. x)"  # one-shot
  python3 lambda_tree.py --tree "λf. λx. f (f x)"    # AST tree
  python3 lambda_tree.py --church 5                   # show Church numeral

Inspired by the beauty of computation as pure symbol-rewriting.
"""

import sys
import re
import readline  # better REPL
from enum import Enum, auto
from typing import Optional

# ─── AST Nodes ────────────────────────────────────────────────────────────────

class Node:
    """Base class for λ-expression AST nodes."""
    def __repr__(self): return self.show()
    def free_vars(self) -> set:
        raise NotImplementedError

class Var(Node):
    def __init__(self, name: str):
        self.name = name
    def show(self, _depth=0):
        return self.name
    def free_vars(self):
        return {self.name}
    def subst(self, var: str, replacement: Node) -> Node:
        return replacement if self.name == var else self

class Abs(Node):
    def __init__(self, param: str, body: Node):
        self.param = param
        self.body = body
    def show(self, _depth=0):
        return f"λ{self.param}. {self.body.show()}"
    def free_vars(self):
        return self.body.free_vars() - {self.param}
    def subst(self, var: str, replacement: Node) -> Node:
        if var == self.param:
            return self  # bound variable — no substitution
        fv_repl = replacement.free_vars()
        if self.param not in fv_repl:
            return Abs(self.param, self.body.subst(var, replacement))
        # α-conversion needed
        fresh = fresh_var(self.param, self.body.free_vars() | fv_repl | {var})
        renamed = self.body.subst(self.param, Var(fresh))
        return Abs(fresh, renamed.subst(var, replacement))

class App(Node):
    def __init__(self, left: Node, right: Node):
        self.left = left
        self.right = right
    def show(self, _depth=0):
        l = paren(self.left, is_left=True)
        r = paren(self.right, is_left=False)
        return f"{l} {r}"
    def free_vars(self):
        return self.left.free_vars() | self.right.free_vars()
    def subst(self, var: str, replacement: Node) -> Node:
        return App(self.left.subst(var, replacement),
                   self.right.subst(var, replacement))

def paren(node: Node, is_left: bool) -> str:
    """Add parentheses when needed for pretty-printing"""
    s = node.show()
    if isinstance(node, App):
        return f"({s})"
    if isinstance(node, Abs) and not is_left:
        return f"({s})"
    return s

_var_counter = [0]
def fresh_var(base: str, forbidden: set) -> str:
    _var_counter[0] += 1
    name = f"{base}{_var_counter[0]}"
    while name in forbidden:
        _var_counter[0] += 1
        name = f"{base}{_var_counter[0]}"
    return name

def reset_fresh():
    _var_counter[0] = 0

# ─── Parser ───────────────────────────────────────────────────────────────────

class Token(Enum):
    LAMBDA = auto()
    DOT = auto()
    LPAREN = auto()
    RPAREN = auto()
    VAR = auto()
    EOF = auto()

class Lexer:
    def __init__(self, text: str):
        self.tokens = []
        self.pos = 0
        self.text = text
        self._tokenize(text)

    def _tokenize(self, text: str):
        i = 0
        while i < len(text):
            ch = text[i]
            if ch in ' \t\n\r':
                i += 1
                continue
            if ch == '\\':
                self.tokens.append((Token.LAMBDA, '\\'))
                i += 1
            elif ch == 'λ':
                self.tokens.append((Token.LAMBDA, 'λ'))
                i += 1
            elif ch == '.':
                self.tokens.append((Token.DOT, '.'))
                i += 1
            elif ch == '(':
                self.tokens.append((Token.LPAREN, '('))
                i += 1
            elif ch == ')':
                self.tokens.append((Token.RPAREN, ')'))
                i += 1
            elif ch.isalpha() or ch in '_':
                j = i
                while j < len(text) and (text[j].isalpha() or text[j].isdigit() or text[j] in "_'"):
                    j += 1
                self.tokens.append((Token.VAR, text[i:j]))
                i = j
            else:
                i += 1  # skip unknown
        self.tokens.append((Token.EOF, ''))

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (Token.EOF, '')

    def advance(self):
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

class Parser:
    def __init__(self, text: str):
        self.lex = Lexer(text)

    def parse(self) -> Node:
        # Preprocess: expand combinator macros
        expanded = preprocess(self.lex.text)
        if expanded != self.lex.text:
            self.lex = Lexer(expanded)
        reset_fresh()
        node = self._expr()
        if self.lex.peek()[0] != Token.EOF:
            raise SyntaxError(f"Unexpected token: {self.lex.peek()}")
        return node

    def _expr(self) -> Node:
        """expr := lambda | application"""
        tok, val = self.lex.peek()
        if tok == Token.LAMBDA:
            return self._lambda()
        return self._application()

    def _lambda(self) -> Node:
        self.lex.advance()  # consume λ
        params = []
        while self.lex.peek()[0] == Token.VAR:
            _, p = self.lex.advance()
            params.append(p)
        if self.lex.peek()[0] != Token.DOT:
            raise SyntaxError("Expected '.' after parameters")
        self.lex.advance()
        body = self._expr()
        # Multi-param λx. λy. body  →  λx. λy. body
        for p in reversed(params):
            body = Abs(p, body)
        return body

    def _application(self) -> Node:
        left = self._atom()
        while True:
            tok, _ = self.lex.peek()
            if tok in (Token.VAR, Token.LPAREN, Token.LAMBDA):
                left = App(left, self._atom())
            else:
                break
        return left

    def _atom(self) -> Node:
        tok, val = self.lex.peek()
        if tok == Token.VAR:
            self.lex.advance()
            return Var(val)
        elif tok == Token.LPAREN:
            self.lex.advance()
            node = self._expr()
            if self.lex.peek()[0] != Token.RPAREN:
                raise SyntaxError("Missing ')'")
            self.lex.advance()
            return node
        elif tok == Token.LAMBDA:
            return self._lambda()
        else:
            raise SyntaxError(f"Unexpected token: {tok}")

# ─── Reduction ────────────────────────────────────────────────────────────────

class Strategy(Enum):
    NORMAL = "normal order"       # leftmost, outermost first (normalizing)
    CBN = "call-by-name"          # leftmost, leftmost — no reduction under λ
    CBV = "call-by-value"         # leftmost, outermost — but only when arg is a value

def is_value(node: Node, strategy: Strategy) -> bool:
    """Is the node fully reduced (a value) under given strategy?"""
    if isinstance(node, Abs):
        return True
    if isinstance(node, Var):
        return True
    return False

def beta_reduce(node: Node, strategy: Strategy = Strategy.CBV) -> Node:
    """Perform one β-reduction step. Returns (reduced_node, did_reduce, path_string)."""
    if isinstance(node, Var):
        return node, False, ""

    if isinstance(node, Abs):
        body, changed, path = beta_reduce(node.body, strategy)
        if changed:
            return Abs(node.param, body), True, path
        return node, False, ""

    if isinstance(node, App):
        # β-redex: (λx. body) arg
        if isinstance(node.left, Abs):
            # Substitute
            result = node.left.body.subst(node.left.param, node.right)
            return result, True, f"β: ({node.left.show()} {node.right.show()})"

        # Normal order: reduce left first
        left, changed_l, path_l = beta_reduce(node.left, strategy)
        if changed_l:
            return App(left, node.right), True, path_l

        # For CBV, reduce right to a value before applying
        if strategy == Strategy.CBV and not is_value(node.right, strategy):
            right, changed_r, path_r = beta_reduce(node.right, strategy)
            if changed_r:
                return App(node.left, right), True, path_r

        # CBN: don't reduce under λ
        if strategy == Strategy.CBN and isinstance(node.left, Abs):
            return node, False, ""

        # Normal order: reduce right too
        if strategy == Strategy.NORMAL:
            right, changed_r, path_r = beta_reduce(node.right, strategy)
            if changed_r:
                return App(node.left, right), True, path_r

        return node, False, ""

    return node, False, ""

def reduce_fully(node: Node, strategy: Strategy = Strategy.CBV, max_steps: int = 1000) -> list:
    """Reduce fully, returning list of (step_num, node, path) tuples."""
    steps = [(0, node, "start")]
    current = node
    for i in range(max_steps):
        current, changed, path = beta_reduce(current, strategy)
        if not changed:
            break
        steps.append((i + 1, current, path))
    return steps

# ─── ASCII Tree Visualisation ────────────────────────────────────────────────

def ascii_tree(node: Node) -> str:
    """Render the AST as an ASCII tree"""
    lines = []
    _tree_lines(node, lines, "", True)
    return "".join(lines)

def _tree_lines(node: Node, lines: list, prefix: str, is_last: bool):
    connector = "└── " if is_last else "├── "
    if isinstance(node, Var):
        lines.append(f"{prefix}{connector}Var({node.name})\n")
    elif isinstance(node, Abs):
        lines.append(f"{prefix}{connector}λ {node.param}\n")
        ext = "    " if is_last else "│   "
        _tree_lines(node.body, lines, prefix + ext, True)
    elif isinstance(node, App):
        lines.append(f"{prefix}{connector}App\n")
        ext = "    " if is_last else "│   "
        _tree_lines(node.left, lines, prefix + ext, False)
        _tree_lines(node.right, lines, prefix + ext, True)

# ─── Church Numerals ──────────────────────────────────────────────────────────

def church_numeral(n: int) -> Node:
    """Church numeral: λf. λx. f (f (... f x))   (n times)"""
    if n == 0:
        return Abs("f", Abs("x", Var("x")))
    f = Var("f")
    x = Var("x")
    body = x
    for _ in range(n):
        body = App(f, body)
    return Abs("f", Abs("x", body))

def decode_church(node: Node) -> Optional[int]:
    """Try to decode a Church numeral back to int"""
    if not isinstance(node, Abs):
        return None
    if not isinstance(node.body, Abs):
        return None
    f_var = node.param
    x_var = node.body.param
    body = node.body.body
    count = 0
    while isinstance(body, App) and isinstance(body.left, Var) and body.left.name == f_var:
        count += 1
        body = body.right
    if isinstance(body, Var) and body.name == x_var:
        return count
    return None

# ─── Combinator Library ───────────────────────────────────────────────────────

COMBINATORS = {
    "I": Abs("x", Var("x")),
    "K": Abs("x", Abs("y", Var("x"))),
    "KI": Abs("x", Abs("y", Var("y"))),
    "S": Abs("x", Abs("y", Abs("z", App(App(Var("x"), Var("z")), App(Var("y"), Var("z")))))),
    "B": Abs("x", Abs("y", Abs("z", App(Var("x"), App(Var("y"), Var("z")))))),
    "C": Abs("x", Abs("y", Abs("z", App(App(Var("x"), Var("z")), Var("y"))))),
    "W": Abs("x", Abs("y", App(App(Var("x"), Var("y")), Var("y")))),
    "Y": Abs("f", App(Abs("x", App(Var("f"), App(Var("x"), Var("x")))),
                       Abs("x", App(Var("f"), App(Var("x"), Var("x")))))),
    "TRUE": Abs("t", Abs("f", Var("t"))),
    "FALSE": Abs("t", Abs("f", Var("f"))),
}

# ─── REPL ─────────────────────────────────────────────────────────────────────

BANNER = """
╔══════════════════════════════════════════════════════╗
║                 λ-tree  —  λ-Calculus               ║
║         Visualise · Reduce · Explore                ║
╚══════════════════════════════════════════════════════╝

Commands:
  :tree <expr>       Show AST tree
  :reduce <expr>     Step through β-reduction
  :church <n>        Show Church numeral n
  :decode <expr>     Try to decode Church numeral
  :combinators       List available combinators
  :help              Show this help
  :quit              Exit

Examples:
  (λx. x) y            → simple identity
  (λx. x x) (λx. x)   → Ω reduces to itself
  λf. λx. f (f x)      → Church numeral 2
  S K K                → equivalent to I
  (λx. λy. x) a b      → K combinator
  Y                    → fixed-point combinator
"""

def format_step(step_num: int, node: Node, path: str) -> str:
    """Format a single reduction step for display."""
    if step_num == 0:
        return f"  ⟹  {node.show()}"
    return f"  {step_num:2d}. {path}  ⟹  {node.show()}"

def preprocess(text: str) -> str:
    """Expand combinator names in source text before parsing."""
    tokens = re.findall(r"[\w'_]+|\\|λ|[.()]|\S", text)
    result = []
    for tok in tokens:
        if tok in COMBINATORS:
            result.append("(" + COMBINATORS[tok].show() + ")")
        else:
            result.append(tok)
    return " ".join(result)


def main():
    args = [a for a in sys.argv[1:] if a]

    if not args:
        # Interactive REPL
        print(BANNER)
        try:
            import readline
        except ImportError:
            pass
        while True:
            try:
                line = input("λ> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue
            if line.startswith(":"):
                cmd = line[1:].strip()
                if cmd == "quit":
                    break
                elif cmd == "help":
                    print(BANNER)
                elif cmd == "combinators":
                    print("  Available combinators:")
                    for name, node in sorted(COMBINATORS.items()):
                        print(f"    {name:6s} = {node.show()}")
                elif cmd.startswith("tree ") or cmd.startswith("tree "):
                    rest = cmd[5:].strip()
                    try:
                        node = Parser(rest).parse()
                        print(ascii_tree(node))
                    except (SyntaxError, Exception) as e:
                        print(f"  ✗ Parse error: {e}")
                elif cmd.startswith("reduce "):
                    rest = cmd[7:].strip()
                    strategy = Strategy.CBV
                    if " --cbn" in rest:
                        strategy = Strategy.CBN
                        rest = rest.replace(" --cbn", "")
                    if " --normal" in rest:
                        strategy = Strategy.NORMAL
                        rest = rest.replace(" --normal", "")
                    try:
                        node = Parser(rest).parse()
                        steps = reduce_fully(node, strategy)
                        print(f"  Strategy: {strategy.value}")
                        for s in steps:
                            print(format_step(*s))
                        if steps[-1][1] != node:
                            dec = decode_church(steps[-1][1])
                            if dec is not None:
                                print(f"\n  Church numeral → {dec}")
                    except (SyntaxError, Exception) as e:
                        print(f"  ✗ Error: {e}")
                elif cmd.startswith("church "):
                    try:
                        n = int(cmd[7:].strip())
                        node = church_numeral(n)
                        print(f"  Church numeral {n}:")
                        print(f"    {node.show()}")
                        print(f"\n  Tree:")
                        print(ascii_tree(node))
                    except ValueError:
                        print("  ✗ Usage: :church <int>")
                elif cmd.startswith("decode "):
                    rest = cmd[7:].strip()
                    try:
                        node = Parser(rest).parse()
                        dec = decode_church(node)
                        if dec is not None:
                            print(f"  Church numeral → {dec}")
                        else:
                            # Try reducing first
                            print("  Not a Church numeral. Trying reduction...")
                            steps = reduce_fully(node, Strategy.NORMAL, 200)
                            final = steps[-1][1]
                            dec = decode_church(final)
                            if dec is not None:
                                print(f"  After reduction: {final.show()}")
                                print(f"  Church numeral → {dec}")
                            else:
                                print(f"  Reduced to: {final.show()}")
                                print(f"  Still not a Church numeral.")
                    except (SyntaxError, Exception) as e:
                        print(f"  ✗ Error: {e}")
                else:
                    print(f"  Unknown command: {line}")
            else:
                # Evaluate expression
                try:
                    node = Parser(line).parse()
                    steps = reduce_fully(node, Strategy.CBV, 200)
                    for s in steps:
                        print(format_step(*s))
                except (SyntaxError, Exception) as e:
                    print(f"  ✗ Error: {e}")
        return

    # Non-interactive
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--tree" and i + 1 < len(args):
            i += 1
            try:
                node = Parser(args[i]).parse()
                print(ascii_tree(node))
            except Exception as e:
                print(f"Parse error: {e}", file=sys.stderr)
        elif a == "--eval" and i + 1 < len(args):
            i += 1
            try:
                node = Parser(args[i]).parse()
                steps = reduce_fully(node, Strategy.CBV, 200)
                for s in steps:
                    print(format_step(*s))
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
        elif a == "--church" and i + 1 < len(args):
            i += 1
            try:
                n = int(args[i])
                node = church_numeral(n)
                print(f"Church {n} = {node.show()}")
                print(ascii_tree(node))
            except ValueError:
                print(f"Invalid number: {args[i]}", file=sys.stderr)
        elif a == "--reduce" and i + 1 < len(args):
            i += 1
            strategy = Strategy.CBV
            rest = args[i]
            if rest == "--cbn" and i + 1 < len(args):
                strategy = Strategy.CBN
                i += 1
                rest = args[i]
            elif rest == "--normal" and i + 1 < len(args):
                strategy = Strategy.NORMAL
                i += 1
                rest = args[i]
            try:
                node = Parser(rest).parse()
                steps = reduce_fully(node, strategy)
                print(f"Strategy: {strategy.value}")
                for s in steps:
                    print(format_step(*s))
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
        i += 1

if __name__ == "__main__":
    main()
