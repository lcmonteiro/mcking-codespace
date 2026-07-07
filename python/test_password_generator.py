#!/usr/bin/env python3
"""
Test script for password_generator.py
"""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the password generator functions
from password_generator import (
    generate_password,
    calculate_strength_score,
    get_strength_feedback,
    get_strength_color,
    draw_strength_bar,
    CHAR_SETS,
    PRESETS
)

def test_password_generation():
    """Test password generation."""
    print("Testing password generation...")
    
    # Test default generation
    password = generate_password()
    print(f"Default password: {password}")
    assert len(password) == 16, f"Expected length 16, got {len(password)}"
    
    # Test custom length
    password = generate_password(length=20)
    print(f"Custom length (20): {password}")
    assert len(password) == 20, f"Expected length 20, got {len(password)}"
    
    # Test with specific character sets
    password = generate_password(length=12, char_sets=['lower', 'digits'])
    print(f"Lower + digits: {password}")
    assert all(c in CHAR_SETS['lower'] + CHAR_SETS['digits'] for c in password)
    
    # Test without ambiguous characters
    password = generate_password(exclude_ambiguous=True)
    print(f"No ambiguous: {password}")
    ambiguous_chars = CHAR_SETS['ambiguous']
    assert not any(c in ambiguous_chars for c in password), "Found ambiguous characters"
    
    print("[OK] Password generation tests passed!\n")

def test_strength_calculation():
    """Test strength calculation."""
    print("Testing strength calculation...")
    
    # Weak password
    weak_pwd = "password123"
    score = calculate_strength_score(weak_pwd)
    print(f"Weak password score: {score}")
    assert score < 40, f"Weak password should score < 40, got {score}"
    
    # Strong password
    strong_pwd = "Xk9#mP2@qR1!vY8$"
    score = calculate_strength_score(strong_pwd)
    print(f"Strong password score: {score}")
    assert score > 60, f"Strong password should score > 60, got {score}"
    
    # Very strong password
    very_strong = "aB1!kL9@mN2#oP4$qR7%"
    score = calculate_strength_score(very_strong)
    print(f"Very strong password score: {score}")
    assert score > 80, f"Very strong password should score > 80, got {score}"
    
    print("[OK] Strength calculation tests passed!\n")

def test_strength_colors():
    """Test strength color mapping."""
    print("Testing strength colors...")
    
    color, label = get_strength_color(90)
    print(f"Score 90: {color}, {label}")
    assert "Very Strong" in label
    
    color, label = get_strength_color(70)
    print(f"Score 70: {color}, {label}")
    assert "Strong" in label
    
    color, label = get_strength_color(50)
    print(f"Score 50: {color}, {label}")
    assert "Medium" in label
    
    color, label = get_strength_color(30)
    print(f"Score 30: {color}, {label}")
    assert "Weak" in label
    
    color, label = get_strength_color(10)
    print(f"Score 10: {color}, {label}")
    assert "Very Weak" in label
    
    print("[OK] Strength color tests passed!\n")

def test_presets():
    """Test preset configurations."""
    print("Testing presets...")
    
    for name, config in PRESETS.items():
        password = generate_password(**config)
        print(f"Preset '{name}': {password} (length: {len(password)})")
        assert len(password) == config['length']
    
    print("[OK] Preset tests passed!\n")

def test_feedback():
    """Test password feedback."""
    print("Testing feedback...")
    
    # Test with weak password
    feedback = get_strength_feedback("password")
    print(f"Feedback for 'password': {feedback}")
    assert feedback['score'] < 2
    
    # Test with strong password
    feedback = get_strength_feedback("Xk9#mP2@qR1!vY8$")
    print(f"Feedback for strong password: {feedback}")
    assert feedback['score'] >= 3
    
    print("[OK] Feedback tests passed!\n")

def main():
    """Run all tests."""
    print("=" * 60)
    print("Password Generator - Test Suite")
    print("=" * 60 + "\n")
    
    try:
        test_password_generation()
        test_strength_calculation()
        test_strength_colors()
        test_presets()
        test_feedback()
        
        print("=" * 60)
        print("[SUCCESS] ALL TESTS PASSED!")
        print("=" * 60)
        return 0
        
    except Exception as e:
        print(f"[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
