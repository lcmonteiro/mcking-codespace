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

*Part of the [Mcking Codespace](https://github.com/lcmonteiro/mcking-codespace) project*
