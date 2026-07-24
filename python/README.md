## Python Projects

| Script | Description |
|---|---|
| [`hyperspace.py`](./hyperspace.py) | 🚀 Hyperspace starfield with warp drive, palette cycling, interactive controls |
| [`password_generator.py`](./password_generator.py) | 🔐 Password Generator & Strength Analyzer |
| [`lambda_tree.py`](./lambda_tree.py) | λ λ-calculus visualiser with β-reduction, ASCII trees, Church numerals |
| [`nocturne.py`](./nocturne.py) | 🌙 Animated night landscape in terminal |
| [`plasma.py`](./plasma.py) | 🔮 Classic demoscene plasma effect |
| [`mandelbrot.py`](./mandelbrot.py) | 🌀 Interactive Mandelbrot set explorer |
| [`cellular_automata.py`](./cellular_automata.py) | 🧬 Cellular automata playground (6 rulesets) |
| [`aurora.py`](./aurora.py) | 🌌 Animated aurora borealis effect |
| [`maze_generator.py`](./maze_generator.py) | 🏗️ Maze generation & solving |
| [`matrix_rain.py`](./matrix_rain.py) | 💚 Matrix digital rain |
| [`fractal_ascii.py`](./fractal_ascii.py) | 🔷 ASCII fractal renderer |
| [`cyberdash.py`](./cyberdash.py) | ⚡ Cyberpunk dashboard |
| [`lifelike.py`](./lifelike.py) | 🧪 Life-like cellular automata |
| [`snake.py`](./snake.py) | 🐍 Terminal Snake game — arrow/WASD, pause, score, speed scaling |
| [`lorenz.py`](./lorenz.py) | 🦋 Lorenz Attractor — 3D chaotic system, rotating ASCII, ANSI colour |

---

# 🔐 Password Generator & Strength Analyzer

An interactive password generator and strength analyzer tool for secure password management.

## 🚀 Features

- **Password Generation**
  - Generate single or multiple passwords
  - Customizable length (4-128 characters)
  - Multiple character sets: lowercase, uppercase, digits, symbols
  - Exclude ambiguous characters option
  - Ensure at least one character from each selected set

- **Strength Analysis**
  - Advanced strength calculation using [zxcvbn](https://github.com/dropbox/zxcvbn)
  - Visual strength meter with color-coded feedback
  - Detailed crack time estimates
  - Improvement suggestions

- **Preset Configurations**
  - **Weak**: 8 characters, lowercase + digits
  - **Medium**: 12 characters, lowercase + uppercase + digits
  - **Strong**: 16 characters, all sets except special symbols
  - **Insane**: 24 characters, all character sets

- **User Interface**
  - Interactive menu system
  - Color-coded output
  - Copy to clipboard functionality

## 📦 Installation

```bash
# Clone the repository
cd mcking-codespace

# Install dependencies
pip install zxcvbn colorama pyperclip
```

## 🎯 Usage

### Run the generator

```bash
python python/password_generator.py
```

### Run tests

```bash
python python/test_password_generator.py
```

### Command line usage (examples)

```python
# Import the module
from password_generator import generate_password, calculate_strength_score

# Generate a password
password = generate_password(length=16, char_sets=['lower', 'upper', 'digits', 'symbols'])
print(f"Generated: {password}")

# Check strength
score = calculate_strength_score(password)
print(f"Strength: {score}/100")
```

## 📊 Examples

### Generate a strong password
```python
from password_generator import generate_password

password = generate_password(
    length=20,
    char_sets=['lower', 'upper', 'digits', 'symbols'],
    exclude_ambiguous=True,
    require_each_set=True
)
# Output: e.g., "kP9#mX2@qR1!vY8$zW4%"
```

### Analyze password strength
```python
from password_generator import calculate_strength_score, get_strength_feedback

password = "MySecurePassword123!"
score = calculate_strength_score(password)
feedback = get_strength_feedback(password)

print(f"Score: {score}/100")
print(f"Crack time: {feedback['crack_time']}")
print(f"Suggestions: {feedback['feedback']}")
```

## 🎨 Output Preview

```
============================================================
              [LOCK] PASSWORD GENERATOR
     Secure & Interactive Password Tool
============================================================

[MENU] MAIN MENU
1. Generate single password
2. Generate multiple passwords
3. Analyze existing password
4. Use preset configurations
5. Custom password generation
0. Exit

Select an option: 1

[LOCK] Generating Single Password

Password #1:
 ███████████████████████████████████████████████████████
[++++] Very Strong
Crack time: centuries

Copy to clipboard? (y/n): y
✅ Password copied to clipboard!
```

## 🔧 Configuration

### Character Sets

| Set | Characters |
|-----|------------|
| `lower` | a-z |
| `upper` | A-Z |
| `digits` | 0-9 |
| `symbols` | `!@#$%^&*()_+-=[]{}\|;:,.<>?` |
| `all_symbols` | Extended symbol set |

### Ambiguous Characters

The following characters are excluded by default:
```
{}[]()/\"'`~\n\t 
```

## 📈 Strength Levels

| Score Range | Rating | Color |
|-------------|--------|-------|
| 80-100 | Very Strong | Green |
| 60-79 | Strong | Cyan |
| 40-59 | Medium | Yellow |
| 20-39 | Weak | Magenta |
| 0-19 | Very Weak | Red |

## 🛡️ Security Notes

- **Never share generated passwords**
- **Store passwords securely** in a password manager
- **Use unique passwords** for different services
- **Enable 2FA** whenever possible
- **Rotate passwords** regularly

## 📝 Changelog

- **v1.0.0** (2026-07-07): Initial release
  - Complete password generator
  - Strength analysis with zxcvbn
  - Interactive menu system
  - Comprehensive test suite

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

## 🙏 Credits

- **Author**: Mcking (AI Assistant)
- **Date**: July 7, 2026
- **Inspired by**: zxcvbn password strength estimator

---

---

# λ λ-tree — Lambda Calculus Visualiser

A terminal-based lambda calculus expression explorer and visualiser.

## Quick Start

```bash
# Evaluate an expression (CBV)
python python/lambda_tree.py --eval "(λx. x x) (λx. x)"

# Show AST tree
python python/lambda_tree.py --tree "λf. λx. f (f x)"

# Show Church numeral
python python/lambda_tree.py --church 5

# Reduce with normal order strategy
python python/lambda_tree.py --reduce "S K K" --normal
```

## Interactive REPL

```bash
python python/lambda_tree.py
```

```
λ> (λx. x) y
  ⟹  y

λ> :reduce S K K --normal
  Strategy: normal order
  ⟹  (λx. λy. λz. (x z) (y z) (λx. λy. x)) (λx. λy. x)
   1. β: ...  ⟹  λz. z

λ> :tree λf. λx. f (f (f x))
└── λ f
    └── λ x
        └── App
            ├── Var(f)
            └── App (...)

λ> :church 5
  Church numeral 5:
    λf. λx. f (f (f (f (f x))))

λ> :decode λf. λx. f (f (f x))
  Church numeral → 3

λ> :combinators
    B      = λx. λy. λz. x (y z)
    C      = λx. λy. λz. (x z) y
    I      = λx. x
    K      = λx. λy. x
    S      = λx. λy. λz. (x z) (y z)
    Y      = λf. λx. f (x x) (λx. f (x x))
    ...
```

## Features

- **Parser**: Variables, abstractions (λ/\), applications
- **β-reduction**: Three strategies (CBV, CBN, Normal Order)
- **α-conversion**: Automatic renaming to avoid capture
- **ASCII Tree**: Visual AST representation
- **Church Numerals**: Encode/decode natural numbers
- **Combinator Library**: S, K, I, B, C, W, Y, TRUE, FALSE
- **Interactive REPL** with command history (readline)

## REPL Commands

| Command | Description |
|---|---|
| `:tree <expr>` | Show AST tree |
| `:reduce <expr>` | Step through β-reduction |
| `:reduce <expr> --cbn` | Call-by-name reduction |
| `:reduce <expr> --normal` | Normal order reduction |
| `:church <n>` | Show Church numeral n |
| `:decode <expr>` | Try to decode Church numeral |
| `:combinators` | List available combinators |
| `:help` | Show help banner |
| `:quit` | Exit |


---

*Part of the [Mcking Codespace](https://github.com/lcmonteiro/mcking-codespace) project*
