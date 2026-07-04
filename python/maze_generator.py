#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Maze Generator - Labirinto Perfeito com Algoritmo de Prim

Gera labirintos perfeitos (sem ilhas, caminho unico entre quaisquer dois pontos)
usando o algoritmo de Prim. Visualizacao ASCII interativa no terminal.

Uso:
    python maze_generator.py [linhas] [colunas]
    python maze_generator.py 20 40  # labirinto 20x40

Controles (modo interativo):
    Setas: navegar
    R: reiniciar (novo labirinto)
    P: alternar caminho
    S: guardar como imagem (se PIL disponivel)
    Q: sair

Autor: Mcking (AI assistant do Luis Monteiro)
Data: 2026-07-04
"""

import sys
import random
import time
import argparse
from enum import Enum
from typing import List, Tuple, Optional

# Windows UTF-8 stdout fix
if sys.platform == "win32":
    import os
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class Direction(Enum):
    NORTH = (0, -1)
    SOUTH = (0, 1)
    EAST = (1, 0)
    WEST = (-1, 0)


class MazeGenerator:
    """Gerador de labirintos usando algoritmo de Prim."""
    
    def __init__(self, width: int = 20, height: int = 20):
        self.width = max(5, width // 2 * 2 + 1)  # garantir impar
        self.height = max(5, height // 2 * 2 + 1)  # garantir impar
        self.grid = [[1 for _ in range(self.width)] for _ in range(self.height)]
        self.visited = [[False for _ in range(self.width)] for _ in range(self.height)]
        self.start = (1, 1)
        self.end = (self.width - 2, self.height - 2)
        
    def generate(self) -> None:
        """Gera labirinto usando algoritmo de Prim."""
        # Comecar com uma celula aleatoria
        start_x, start_y = random.randrange(1, self.width, 2), random.randrange(1, self.height, 2)
        self.grid[start_y][start_x] = 0
        self.visited[start_y][start_x] = True
        self.start = (start_x, start_y)
        
        # Lista de paredes (frontier)
        walls = self._get_neighbor_walls(start_x, start_y)
        
        while walls:
            # Escolher parede aleatoria
            wall_idx = random.randrange(len(walls))
            wx, wy, direction = walls[wall_idx]
            
            # Verificar se a celula do outro lado ja foi visitada
            nx, ny = wx + direction.value[0], wy + direction.value[1]
            
            if not self.visited[ny][nx]:
                # Remover parede
                self.grid[wy][wx] = 0
                self.grid[ny][nx] = 0
                self.visited[ny][nx] = True
                
                # Adicionar novas paredes a frontier
                walls.extend(self._get_neighbor_walls(nx, ny))
            
            # Remover esta parede da lista
            del walls[wall_idx]
        
        # Garantir que start e end sao caminhos
        self.grid[self.start[1]][self.start[0]] = 0
        self.grid[self.end[1]][self.end[0]] = 0
        self.visited[self.start[1]][self.start[0]] = True
        self.visited[self.end[1]][self.end[0]] = True
        
    def _get_neighbor_walls(self, x: int, y: int) -> List[Tuple[int, int, Direction]]:
        """Obtem paredes vizinhas de uma celula."""
        walls = []
        for direction in Direction:
            wx, wy = x + direction.value[0], y + direction.value[1]
            # Verificar se esta dentro dos limites
            if 0 <= wx < self.width and 0 <= wy < self.height:
                # Verificar se e parede e se a celula do outro lado existe
                nx, ny = wx + direction.value[0], wy + direction.value[1]
                if (0 <= nx < self.width and 0 <= ny < self.height and 
                    self.grid[wy][wx] == 1 and self.grid[ny][nx] == 1):
                    walls.append((wx, wy, direction))
        return walls
    
    def find_path(self, start: Optional[Tuple[int, int]] = None, end: Optional[Tuple[int, int]] = None) -> List[Tuple[int, int]]:
        """Encontra caminho entre dois pontos usando BFS."""
        if start is None:
            start = self.start
        if end is None:
            end = self.end
        
        from collections import deque
        queue = deque([[start]])
        visited = {start}
        
        while queue:
            path = queue.popleft()
            x, y = path[-1]
            
            if (x, y) == end:
                return path
            
            for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                nx, ny = x + dx, y + dy
                if (0 <= nx < self.width and 0 <= ny < self.height and 
                    self.grid[ny][nx] == 0 and (nx, ny) not in visited):
                    visited.add((nx, ny))
                    queue.append(path + [(nx, ny)])
        
        return []
    
    def to_ascii(self, player_pos: Optional[Tuple[int, int]] = None, show_path: bool = False) -> str:
        """Converte labirinto para ASCII art."""
        path = self.find_path() if show_path else []
        
        result = []
        for y in range(self.height):
            row = []
            for x in range(self.width):
                if (x, y) == self.start:
                    row.append('S')
                elif (x, y) == self.end:
                    row.append('E')
                elif player_pos and (x, y) == player_pos:
                    row.append('P')
                elif (x, y) in path:
                    row.append('.')
                elif self.grid[y][x] == 1:
                    row.append('#')
                else:
                    row.append(' ')
            result.append(''.join(row))
        
        return '\n'.join(result)
    
    def to_image(self, cell_size: int = 20, show_path: bool = True) -> Optional[Image.Image]:
        """Converte labirinto para imagem PIL."""
        if not HAS_PIL:
            return None
        
        path = self.find_path() if show_path else []
        
        img_width = self.width * cell_size
        img_height = self.height * cell_size
        img = Image.new('RGB', (img_width, img_height), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        
        # Desenhar labirinto
        for y in range(self.height):
            for x in range(self.width):
                if self.grid[y][x] == 1:  # Parede
                    draw.rectangle([
                        x * cell_size, y * cell_size,
                        (x + 1) * cell_size, (y + 1) * cell_size
                    ], fill=(0, 0, 0))
                elif (x, y) == self.start:
                    draw.rectangle([
                        x * cell_size, y * cell_size,
                        (x + 1) * cell_size, (y + 1) * cell_size
                    ], fill=(0, 255, 0))
                elif (x, y) == self.end:
                    draw.rectangle([
                        x * cell_size, y * cell_size,
                        (x + 1) * cell_size, (y + 1) * cell_size
                    ], fill=(255, 0, 0))
                elif (x, y) in path:
                    draw.rectangle([
                        x * cell_size, y * cell_size,
                        (x + 1) * cell_size, (y + 1) * cell_size
                    ], fill=(0, 0, 255))
        
        return img


class InteractiveMaze:
    """Modo interativo para navegar no labirinto."""
    
    def __init__(self, maze: MazeGenerator):
        self.maze = maze
        self.player_pos = list(maze.start)
        self.show_path = False
        
    def draw(self) -> None:
        """Desenha o labirinto no terminal."""
        print("\033[H\033[J", end="")  # Clear screen (ANSI)
        print(f"Labirinto {self.maze.width}x{self.maze.height} | Pos: ({self.player_pos[0]}, {self.player_pos[1]})")
        print("Controles: Setas (navegar), R (reiniciar), P (caminho), S (guardar), Q (sair)")
        print("-" * 50)
        print(self.maze.to_ascii(tuple(self.player_pos), self.show_path))
        print("-" * 50)
        
        # Verificar se chegou ao fim
        if tuple(self.player_pos) == self.maze.end:
            print("PARABENS! Chegaste ao fim do labirinto!")
    
    def move(self, direction: Direction) -> bool:
        """Move o jogador numa direcao. Retorna True se o movimento foi valido."""
        dx, dy = direction.value
        new_x, new_y = self.player_pos[0] + dx, self.player_pos[1] + dy
        
        if (0 <= new_x < self.maze.width and 0 <= new_y < self.maze.height and
            self.maze.grid[new_y][new_x] == 0):
            self.player_pos = [new_x, new_y]
            return True
        return False
    
    def run(self) -> None:
        """Executa o modo interativo."""
        try:
            import msvcrt
            
            self.draw()
            
            while True:
                if msvcrt.kbhit():
                    key = msvcrt.getwch()
                    
                    # Handle arrow keys (they come as two bytes)
                    if key == b'\xe0':
                        key2 = msvcrt.getwch()
                        if key2 == b'H':  # Up arrow
                            self.move(Direction.NORTH)
                        elif key2 == b'P':  # Down arrow
                            self.move(Direction.SOUTH)
                        elif key2 == b'K':  # Left arrow
                            self.move(Direction.WEST)
                        elif key2 == b'M':  # Right arrow
                            self.move(Direction.EAST)
                    elif key == b'r' or key == b'R':
                        # Reiniciar
                        self.maze = MazeGenerator(self.maze.width, self.maze.height)
                        self.maze.generate()
                        self.player_pos = list(self.maze.start)
                    elif key == b'p' or key == b'P':
                        self.show_path = not self.show_path
                    elif key == b's' or key == b'S':
                        if HAS_PIL:
                            self._save_image()
                        else:
                            print("PIL nao disponivel para guardar imagem")
                            time.sleep(1)
                    elif key == b'q' or key == b'Q':
                        break
                    
                    self.draw()
                else:
                    time.sleep(0.05)
                    
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"Erro: {e}")
    
    def _save_image(self) -> None:
        """Guarda o labirinto como imagem."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"maze_{self.maze.width}x{self.maze.height}_{timestamp}.png"
        img = self.maze.to_image(show_path=self.show_path)
        if img:
            img.save(filename)
            print(f"Imagem guardada: {filename}")
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser(
        description="Maze Generator - Labirinto Perfeito com Algoritmo de Prim"
    )
    parser.add_argument(
        "width", 
        nargs="?", 
        type=int, 
        default=31,
        help="Largura do labirinto (default: 31)"
    )
    parser.add_argument(
        "height", 
        nargs="?", 
        type=int, 
        default=21,
        help="Altura do labirinto (default: 21)"
    )
    parser.add_argument(
        "--save", 
        type=str, 
        default=None,
        help="Guarda como imagem (ex: --save maze.png)"
    )
    parser.add_argument(
        "--no-interactive", 
        action="store_true",
        help="Modo nao interativo (apenas gera e mostra)"
    )
    parser.add_argument(
        "--path", 
        action="store_true",
        help="Mostra o caminho da solucao"
    )
    
    args = parser.parse_args()
    
    print("Maze Generator - a gerar labirinto...")
    
    # Gerar labirinto
    maze = MazeGenerator(args.width, args.height)
    start_time = time.time()
    maze.generate()
    gen_time = time.time() - start_time
    
    print(f"Labirinto gerado em {gen_time:.3f}s ({maze.width}x{maze.height})")
    
    # Guardar como imagem se pedido
    if args.save:
        if HAS_PIL:
            img = maze.to_image(show_path=args.path)
            if img:
                img.save(args.save)
                print(f"Imagem guardada: {args.save}")
        else:
            print("PIL nao disponivel para guardar imagem")
    
    # Mostrar ASCII
    print("\n" + maze.to_ascii(show_path=args.path))
    
    # Modo interativo
    if not args.no_interactive and sys.stdin.isatty():
        print("\nPressiona qualquer tecla para iniciar modo interativo...")
        try:
            import msvcrt
            msvcrt.getwch()
            interactive = InteractiveMaze(maze)
            interactive.run()
        except ImportError:
            print("msvcrt nao disponivel (apenas Windows)")
        except KeyboardInterrupt:
            pass
    
    print("\nSessao terminada!")


if __name__ == "__main__":
    main()
