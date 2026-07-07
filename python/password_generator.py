#!/usr/bin/env python3
"""
🔐 Password Generator & Strength Analyzer
Interactive password generator with visual strength meter

Features:
- Generate secure passwords with customizable options
- Analyze existing passwords for strength
- Visual strength indicator with color-coded feedback
- Copy to clipboard functionality
- Multiple character sets and length options

Author: Mcking (AI Assistant)
Date: 2026-07-07
"""

import sys
import os
import random
import string
import time
import hashlib
import zxcvbn  # Password strength estimation
from typing import Tuple, List, Dict, Optional
from colorama import init, Fore, Style, Back

# Initialize colorama for Windows
init()

# =============================================================================
# Configuration
# =============================================================================

# Character sets
CHAR_SETS = {
    'lower': string.ascii_lowercase,
    'upper': string.ascii_uppercase,
    'digits': string.digits,
    'symbols': '!@#$%^&*()_+-=[]{}|;:,.<>?',
    'ambiguous': '{}[]()/\'~`\n\t ',
    'all_symbols': '!@#$%^&*()_+-=[]{}|;:,.<>?/~`\'\\',
}

# Default configurations
PRESETS = {
    'weak': {'length': 8, 'char_sets': ['lower', 'digits']},
    'medium': {'length': 12, 'char_sets': ['lower', 'upper', 'digits']},
    'strong': {'length': 16, 'char_sets': ['lower', 'upper', 'digits', 'symbols']},
    'insane': {'length': 24, 'char_sets': ['lower', 'upper', 'digits', 'all_symbols']},
}

# =============================================================================
# Helper Functions
# =============================================================================

def clear_screen():
    """Clear the terminal screen."""
    if sys.platform == 'win32':
        os.system('cls')
    else:
        os.system('clear')

def copy_to_clipboard(text: str) -> bool:
    """Copy text to clipboard."""
    try:
        if sys.platform == 'win32':
            import pyperclip
            pyperclip.copy(text)
            return True
        else:
            # Try different methods for Unix-like systems
            try:
                import pyperclip
                pyperclip.copy(text)
                return True
            except ImportError:
                # Fallback to xclip
                import subprocess
                subprocess.run(['xclip', '-selection', 'clipboard'], input=text, check=True)
                return True
    except Exception as e:
        print(f"{Fore.YELLOW}⚠️  Could not copy to clipboard: {e}{Style.RESET_ALL}")
        return False

# =============================================================================
# Password Generation
# =============================================================================

def generate_password(
    length: int = 16,
    char_sets: Optional[List[str]] = None,
    exclude_ambiguous: bool = True,
    require_each_set: bool = True
) -> str:
    """
    Generate a secure random password.
    
    Args:
        length: Length of the password
        char_sets: List of character set names to use
        exclude_ambiguous: Exclude ambiguous characters
        require_each_set: Ensure at least one character from each set
    
    Returns:
        Generated password
    """
    if char_sets is None:
        char_sets = ['lower', 'upper', 'digits', 'symbols']
    
    # Build character pool
    char_pool = ''
    for set_name in char_sets:
        char_pool += CHAR_SETS[set_name]
    
    # Exclude ambiguous characters if requested
    if exclude_ambiguous:
        for char in CHAR_SETS['ambiguous']:
            char_pool = char_pool.replace(char, '')
    
    if not char_pool:
        raise ValueError("No characters available for password generation")
    
    # Generate password
    password_chars = []
    
    # Ensure at least one character from each set if required
    if require_each_set:
        for set_name in char_sets:
            set_chars = CHAR_SETS[set_name]
            if exclude_ambiguous:
                set_chars = ''.join(c for c in set_chars if c not in CHAR_SETS['ambiguous'])
            if set_chars:
                password_chars.append(random.choice(set_chars))
    
    # Fill remaining characters
    remaining_length = length - len(password_chars)
    for _ in range(remaining_length):
        password_chars.append(random.choice(char_pool))
    
    # Shuffle the characters
    random.shuffle(password_chars)
    
    return ''.join(password_chars)

def generate_multiple_passwords(count: int = 5, **kwargs) -> List[str]:
    """Generate multiple passwords with the same parameters."""
    return [generate_password(**kwargs) for _ in range(count)]

# =============================================================================
# Password Strength Analysis
# =============================================================================

def calculate_strength_score(password: str) -> float:
    """
    Calculate password strength score (0-100).
    Uses zxcvbn for advanced analysis.
    """
    try:
        result = zxcvbn.zxcvbn(password)
        # Convert zxcvbn score (0-4) to 0-100 scale
        # with additional factors for length and complexity
        base_score = result['score'] * 25
        
        # Add length bonus (up to 25 points)
        length_bonus = min(len(password) / 4, 25)
        
        # Add entropy bonus (up to 25 points)
        entropy = result['entropy'] if 'entropy' in result else 0
        entropy_bonus = min(entropy / 4, 25)
        
        # Subtract for common patterns
        penalty = 0
        if result['feedback']['warning']:
            penalty = 10
        
        score = base_score + length_bonus + entropy_bonus - penalty
        return max(0, min(100, score))
    except:
        # Fallback to simple calculation
        score = 0
        if len(password) >= 8:
            score += 30
        if len(password) >= 12:
            score += 20
        if any(c.isupper() for c in password):
            score += 10
        if any(c.isdigit() for c in password):
            score += 10
        if any(c in CHAR_SETS['symbols'] for c in password):
            score += 20
        if len(set(password)) > len(password) * 0.7:
            score += 10
        return min(100, score)

def get_strength_feedback(password: str) -> Dict:
    """Get detailed feedback about password strength."""
    try:
        result = zxcvbn.zxcvbn(password)
        return {
            'score': result['score'],
            'entropy': result.get('entropy', 0),
            'crack_time': result['crack_times_display']['offline_slow_hashing_1e4_per_second'],
            'feedback': result['feedback']['suggestions'],
            'warnings': result['feedback']['warning']
        }
    except:
        return {
            'score': 0,
            'entropy': 0,
            'crack_time': 'unknown',
            'feedback': [],
            'warnings': ''
        }

def get_strength_color(score: float) -> Tuple[str, str]:
    """Get color and label for strength score."""
    if score >= 80:
        return Fore.GREEN, "[+++] Very Strong"
    elif score >= 60:
        return Fore.CYAN, "[++] Strong"
    elif score >= 40:
        return Fore.YELLOW, "[+] Medium"
    elif score >= 20:
        return Fore.MAGENTA, "[-] Weak"
    else:
        return Fore.RED, "[---] Very Weak"

def draw_strength_bar(score: float, width: int = 40) -> str:
    """Draw a visual strength bar."""
    filled = int(score / 100 * width)
    empty = width - filled
    
    color, _ = get_strength_color(score)
    bar = color + '█' * filled + Style.RESET_ALL + Fore.WHITE + '█' * empty + Style.RESET_ALL
    
    return f"[{bar}] {score:.1f}/100"

# =============================================================================
# Display Functions
# =============================================================================

def display_password(password: str, strength_score: float, index: int = 0):
    """Display a password with its strength analysis."""
    color, label = get_strength_color(strength_score)
    bar = draw_strength_bar(strength_score)
    
    print(f"\n{Fore.CYAN}Password #{index + 1}:{Style.RESET_ALL}")
    print(f"{Fore.WHITE}{Back.BLACK} {password} {Style.RESET_ALL}")
    print(f"{bar}")
    print(f"{color}{label}{Style.RESET_ALL}")
    
    # Show feedback
    feedback = get_strength_feedback(password)
    if feedback['crack_time'] != 'unknown':
        print(f"{Fore.YELLOW}Crack time: {feedback['crack_time']}{Style.RESET_ALL}")
    
    print()

def display_header():
    """Display the application header."""
    clear_screen()
    print(f"{Fore.MAGENTA}{'=' * 60}{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}{' ' * 15}[LOCK] PASSWORD GENERATOR{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}{' ' * 12}Secure & Interactive Password Tool{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}{'=' * 60}{Style.RESET_ALL}")
    print()

def display_menu():
    """Display the main menu."""
    print(f"{Fore.CYAN}[MENU] MAIN MENU{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}1.{Style.RESET_ALL} Generate single password")
    print(f"{Fore.YELLOW}2.{Style.RESET_ALL} Generate multiple passwords")
    print(f"{Fore.YELLOW}3.{Style.RESET_ALL} Analyze existing password")
    print(f"{Fore.YELLOW}4.{Style.RESET_ALL} Use preset configurations")
    print(f"{Fore.YELLOW}5.{Style.RESET_ALL} Custom password generation")
    print(f"{Fore.RED}0.{Style.RESET_ALL} Exit")
    print()

def display_presets():
    """Display preset configurations."""
    print(f"{Fore.CYAN}[TARGET] PRESET CONFIGURATIONS{Style.RESET_ALL}")
    for name, config in PRESETS.items():
        print(f"{Fore.YELLOW}{name.capitalize()}:{Style.RESET_ALL} Length={config['length']}, Sets={', '.join(config['char_sets'])}")
    print()

# =============================================================================
# Interactive Functions
# =============================================================================

def get_user_input(prompt: str, input_type: type = str, min_val: Optional[int] = None, max_val: Optional[int] = None) -> any:
    """Get validated user input."""
    while True:
        try:
            user_input = input(f"{Fore.GREEN}{prompt}{Style.RESET_ALL} ").strip()
            if not user_input:
                return None
            
            if input_type == bool:
                return user_input.lower() in ['y', 'yes', '1', 'true']
            
            value = input_type(user_input)
            
            if min_val is not None and value < min_val:
                print(f"{Fore.RED}Value must be at least {min_val}{Style.RESET_ALL}")
                continue
            
            if max_val is not None and value > max_val:
                print(f"{Fore.RED}Value must be at most {max_val}{Style.RESET_ALL}")
                continue
            
            return value
            
        except ValueError:
            print(f"{Fore.RED}Invalid input. Please enter a valid {input_type.__name__}{Style.RESET_ALL}")

def select_from_list(options: List[str], prompt: str) -> Optional[int]:
    """Let user select from a list of options."""
    print(f"{Fore.CYAN}{prompt}{Style.RESET_ALL}")
    for i, option in enumerate(options):
        print(f"{Fore.YELLOW}{i + 1}.{Style.RESET_ALL} {option}")
    print(f"{Fore.YELLOW}0.{Style.RESET_ALL} Back")
    print()
    
    choice = get_user_input("Select an option", int, min_val=0, max_val=len(options))
    return choice - 1 if choice and choice > 0 else None

# =============================================================================
# Main Functions
# =============================================================================

def generate_single_password():
    """Generate a single password with default settings."""
    display_header()
    print(f"{Fore.CYAN}[LOCK] Generating Single Password{Style.RESET_ALL}")
    print()
    
    # Use strong preset by default
    config = PRESETS['strong']
    password = generate_password(**config)
    score = calculate_strength_score(password)
    
    display_password(password, score)
    
    # Ask if user wants to copy
    if get_user_input("Copy to clipboard? (y/n)", bool):
        if copy_to_clipboard(password):
            print(f"{Fore.GREEN}✅ Password copied to clipboard!{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}⚠️  Could not copy to clipboard{Style.RESET_ALL}")
    
    input(f"\n{Fore.YELLOW}Press Enter to continue...{Style.RESET_ALL}")

def generate_multiple_passwords_interactive():
    """Generate multiple passwords interactively."""
    display_header()
    print(f"{Fore.CYAN}[PEN] Generate Multiple Passwords{Style.RESET_ALL}")
    print()
    
    count = get_user_input("How many passwords?", int, min_val=1, max_val=20) or 5
    length = get_user_input("Password length?", int, min_val=4, max_val=128) or 16
    
    exclude_ambiguous = get_user_input("Exclude ambiguous characters? (y/n)", bool) or True
    
    # Select character sets
    print(f"\n{Fore.CYAN}Available character sets:{Style.RESET_ALL}")
    for i, name in enumerate(['lower', 'upper', 'digits', 'symbols']):
        print(f"{Fore.YELLOW}{i + 1}.{Style.RESET_ALL} {name}")
    
    selected_indices = get_user_input("Select sets (comma separated, e.g., 1,2,3,4)", str) or "1,2,3,4"
    try:
        selected_sets = [list(CHAR_SETS.keys())[int(i) - 1] for i in selected_indices.split(',') if i.strip()]
    except:
        selected_sets = ['lower', 'upper', 'digits', 'symbols']
    
    print(f"\n{Fore.CYAN}Generating {count} passwords...{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Length: {length}, Sets: {', '.join(selected_sets)}{Style.RESET_ALL}")
    print()
    
    passwords = generate_multiple_passwords(
        count=count,
        length=length,
        char_sets=selected_sets,
        exclude_ambiguous=exclude_ambiguous
    )
    
    # Display all passwords
    for i, pwd in enumerate(passwords):
        score = calculate_strength_score(pwd)
        display_password(pwd, score, i)
    
    # Ask if user wants to copy all
    all_passwords_text = '\n'.join([f"{i+1}. {pwd}" for i, pwd in enumerate(passwords)])
    if get_user_input("\nCopy all passwords to clipboard? (y/n)", bool):
        if copy_to_clipboard(all_passwords_text):
            print(f"{Fore.GREEN}✅ All passwords copied to clipboard!{Style.RESET_ALL}")
    
    input(f"\n{Fore.YELLOW}Press Enter to continue...{Style.RESET_ALL}")

def analyze_existing_password():
    """Analyze an existing password."""
    display_header()
    print(f"{Fore.CYAN}🔍 Password Strength Analyzer{Style.RESET_ALL}")
    print()
    
    password = get_user_input("Enter password to analyze (input is not stored)", str)
    if not password:
        return
    
    score = calculate_strength_score(password)
    display_password(password, score)
    
    # Show detailed feedback
    feedback = get_strength_feedback(password)
    
    if feedback['feedback']:
        print(f"{Fore.CYAN}Suggestions for improvement:{Style.RESET_ALL}")
        for suggestion in feedback['feedback']:
            print(f"  {Fore.YELLOW}• {suggestion}{Style.RESET_ALL}")
    
    if feedback['warnings']:
        print(f"{Fore.RED}Warnings:{Style.RESET_ALL}")
        print(f"  {feedback['warnings']}")
    
    input(f"\n{Fore.YELLOW}Press Enter to continue...{Style.RESET_ALL}")

def use_preset_configurations():
    """Use preset configurations."""
    display_header()
    display_presets()
    
    choice = select_from_list(list(PRESETS.keys()), "Select a preset:")
    if choice is None:
        return
    
    preset_name = list(PRESETS.keys())[choice]
    config = PRESETS[preset_name]
    
    print(f"\n{Fore.CYAN}Using preset: {preset_name.capitalize()}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Configuration: Length={config['length']}, Sets={', '.join(config['sets'])}{Style.RESET_ALL}")
    
    count = get_user_input("\nHow many passwords to generate?", int, min_val=1, max_val=10) or 1
    
    passwords = generate_multiple_passwords(count=count, **config)
    
    for i, pwd in enumerate(passwords):
        score = calculate_strength_score(pwd)
        display_password(pwd, score, i)
    
    # Copy all if multiple
    if count > 1 and get_user_input("\nCopy all to clipboard? (y/n)", bool):
        all_text = '\n'.join([f"{i+1}. {pwd}" for i, pwd in enumerate(passwords)])
        copy_to_clipboard(all_text)
        print(f"{Fore.GREEN}✅ All passwords copied!{Style.RESET_ALL}")
    
    input(f"\n{Fore.YELLOW}Press Enter to continue...{Style.RESET_ALL}")

def custom_password_generation():
    """Custom password generation with full control."""
    display_header()
    print(f"{Fore.CYAN}[GEAR] Custom Password Generation{Style.RESET_ALL}")
    print()
    
    length = get_user_input("Password length:", int, min_val=4, max_val=128) or 16
    
    # Character set selection
    available_sets = ['lower', 'upper', 'digits', 'symbols', 'all_symbols']
    print(f"\n{Fore.CYAN}Character Sets:{Style.RESET_ALL}")
    for i, s in enumerate(available_sets):
        print(f"{Fore.YELLOW}{i + 1}.{Style.RESET_ALL} {s}")
    
    selected = get_user_input("\nSelect character sets (comma separated numbers)", str) or "1,2,3,4"
    try:
        selected_sets = [available_sets[int(i) - 1] for i in selected.split(',') if i.strip()]
    except:
        selected_sets = ['lower', 'upper', 'digits', 'symbols']
    
    exclude_ambiguous = get_user_input("\nExclude ambiguous characters? (y/n)", bool) or True
    require_each = get_user_input("Require at least one from each set? (y/n)", bool) or True
    
    count = get_user_input("\nNumber of passwords to generate:", int, min_val=1, max_val=20) or 1
    
    print(f"\n{Fore.CYAN}Generating...{Style.RESET_ALL}")
    
    passwords = generate_multiple_passwords(
        count=count,
        length=length,
        char_sets=selected_sets,
        exclude_ambiguous=exclude_ambiguous,
        require_each_set=require_each
    )
    
    for i, pwd in enumerate(passwords):
        score = calculate_strength_score(pwd)
        display_password(pwd, score, i)
    
    if count > 1 and get_user_input("\nCopy all to clipboard? (y/n)", bool):
        all_text = '\n'.join([f"{i+1}. {pwd}" for i, pwd in enumerate(passwords)])
        copy_to_clipboard(all_text)
        print(f"{Fore.GREEN}✅ All passwords copied!{Style.RESET_ALL}")
    
    input(f"\n{Fore.YELLOW}Press Enter to continue...{Style.RESET_ALL}")

# =============================================================================
# Main Application
# =============================================================================

def check_dependencies():
    """Check if required dependencies are installed."""
    missing = []
    
    try:
        import zxcvbn
    except ImportError:
        missing.append('zxcvbn')
    
    try:
        import colorama
    except ImportError:
        missing.append('colorama')
    
    if missing:
        print(f"{Fore.YELLOW}⚠️  Missing dependencies: {', '.join(missing)}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Installing...{Style.RESET_ALL}")
        try:
            import subprocess
            subprocess.run([sys.executable, '-m', 'pip', 'install'] + missing, check=True)
            print(f"{Fore.GREEN}✅ Dependencies installed!{Style.RESET_ALL}")
            time.sleep(2)
        except Exception as e:
            print(f"{Fore.RED}❌ Could not install dependencies: {e}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Please install manually: pip install {' '.join(missing)}{Style.RESET_ALL}")
            time.sleep(3)

def main():
    """Main application loop."""
    # Check dependencies
    check_dependencies()
    
    # Import again after potential installation
    global zxcvbn
    try:
        import zxcvbn
    except ImportError:
        print(f"{Fore.RED}zxcvbn is required for password strength analysis{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Install with: pip install zxcvbn{Style.RESET_ALL}")
        return
    
    while True:
        display_header()
        display_menu()
        
        choice = get_user_input("Select an option", int, min_val=0, max_val=5)
        
        if choice == 0:
            print(f"{Fore.GREEN}Goodbye! Stay secure! [WAVE]{Style.RESET_ALL}")
            break
        elif choice == 1:
            generate_single_password()
        elif choice == 2:
            generate_multiple_passwords_interactive()
        elif choice == 3:
            analyze_existing_password()
        elif choice == 4:
            use_preset_configurations()
        elif choice == 5:
            custom_password_generation()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Fore.GREEN}Goodbye!{Style.RESET_ALL}")
        sys.exit(0)
    except Exception as e:
        print(f"{Fore.RED}An error occurred: {e}{Style.RESET_ALL}")
        sys.exit(1)
