"""Board character codes and symbol mappings.

Official board character codes (0-71).
Reference: https://docs.vestaboard.com/docs/characterCodes

Note: Some codes (43, 45, 51, 57, 58, 61) are not defined in the official table.
"""

from typing import Dict, Optional, List


class BoardChars:
    """Board character code mappings - Official codes."""
    
    # Blank/Space
    SPACE = 0       # Black on black / white on white
    
    # Letters A-Z (codes 1-26)
    A = 1
    B = 2
    C = 3
    D = 4
    E = 5
    F = 6
    G = 7
    H = 8
    I = 9
    J = 10
    K = 11
    L = 12
    M = 13
    N = 14
    O = 15
    P = 16
    Q = 17
    R = 18
    S = 19
    T = 20
    U = 21
    V = 22
    W = 23
    X = 24
    Y = 25
    Z = 26
    
    # Numbers - IMPORTANT: 1-9 are 27-35, then 0 is 36
    ONE = 27
    TWO = 28
    THREE = 29
    FOUR = 30
    FIVE = 31
    SIX = 32
    SEVEN = 33
    EIGHT = 34
    NINE = 35
    ZERO = 36
    
    # Punctuation and symbols (official codes)
    EXCLAMATION = 37     # !
    AT = 38              # @
    POUND = 39           # #
    DOLLAR = 40          # $
    LEFT_PAREN = 41      # (
    RIGHT_PAREN = 42     # )
    # 43 is undefined
    DASH = 44            # - (hyphen)
    # 45 is undefined
    PLUS = 46            # +
    AMPERSAND = 47       # &
    EQUALS = 48          # =
    SEMICOLON = 49       # ;
    COLON = 50           # :
    # 51 is undefined
    SINGLE_QUOTE = 52    # '
    DOUBLE_QUOTE = 53    # "
    PERCENT = 54         # %
    COMMA = 55           # ,
    PERIOD = 56          # .
    # 57-58 are undefined
    SLASH = 59           # /
    QUESTION = 60        # ?
    # 61 is undefined
    DEGREE = 62          # ° (Flagship only, Heart on Note)
    
    # Color codes (filled color tiles)
    RED = 63
    ORANGE = 64
    YELLOW = 65
    GREEN = 66
    BLUE = 67
    VIOLET = 68          # Also called Purple
    WHITE = 69           # Black on white board (local API)
    BLACK = 70           # White on white board (local API)
    FILLED = 71          # White on black / black on white (not available for local API)
    
    # Aliases for compatibility
    APOSTROPHE = SINGLE_QUOTE
    HYPHEN = DASH
    HEART = DEGREE  # Code 62 renders as ❤ on Note, ° on Flagship
    
    @classmethod
    def get_char_code(cls, char: str) -> Optional[int]:
        """
        Get character code for a single character.
        
        Args:
            char: Single character to convert
            
        Returns:
            Character code (0-71) or None if not found
        """
        char = char.upper()
        
        # Letters A-Z → codes 1-26
        if 'A' <= char <= 'Z':
            return ord(char) - ord('A') + 1
        
        # Numbers: 1-9 → codes 27-35, 0 → code 36
        if '1' <= char <= '9':
            return ord(char) - ord('1') + 27  # 1→27, 2→28, ..., 9→35
        elif char == '0':
            return 36
        
        # Special characters mapping (official codes)
        special_map = {
            ' ': cls.SPACE,
            '!': cls.EXCLAMATION,
            '@': cls.AT,
            '#': cls.POUND,
            '$': cls.DOLLAR,
            '(': cls.LEFT_PAREN,
            ')': cls.RIGHT_PAREN,
            '-': cls.DASH,
            '+': cls.PLUS,
            '&': cls.AMPERSAND,
            '=': cls.EQUALS,
            ';': cls.SEMICOLON,
            ':': cls.COLON,
            "'": cls.SINGLE_QUOTE,
            '"': cls.DOUBLE_QUOTE,
            '%': cls.PERCENT,
            ',': cls.COMMA,
            '.': cls.PERIOD,
            '/': cls.SLASH,
            '?': cls.QUESTION,
            '°': cls.DEGREE,
            '❤': cls.DEGREE,  # Heart on Note devices shares code 62
            '♥': cls.DEGREE,
        }
        
        return special_map.get(char)
    
    @classmethod
    def get_color_code(cls, color_name: str) -> Optional[int]:
        """
        Get color code by name.
        
        Args:
            color_name: Color name (red, green, blue, etc.)
            
        Returns:
            Color code or None if not found
        """
        color_map = {
            'red': cls.RED,
            'orange': cls.ORANGE,
            'yellow': cls.YELLOW,
            'green': cls.GREEN,
            'blue': cls.BLUE,
            'violet': cls.VIOLET,
            'purple': cls.VIOLET,
            'white': cls.WHITE,
            'black': cls.BLACK,
            'filled': cls.FILLED,
        }
        return color_map.get(color_name.lower())
    
    @classmethod
    def text_to_codes(cls, text: str) -> List[int]:
        """
        Convert text string to list of character codes.
        
        Args:
            text: Text string to convert
            
        Returns:
            List of character codes
        """
        codes = []
        for char in text:
            code = cls.get_char_code(char)
            if code is not None:
                codes.append(code)
            else:
                # Fallback to space if character not found
                codes.append(cls.SPACE)
        return codes


# Weather condition to symbol mapping
WEATHER_SYMBOLS: Dict[str, Dict[str, any]] = {
    "Clear": {
        "symbol": "O",  # Sun approximation
        "char_code": BoardChars.O,
        "description": "Sunny"
    },
    "Sunny": {
        "symbol": "O",
        "char_code": BoardChars.O,
        "description": "Sunny"
    },
    "Partly Cloudy": {
        "symbol": "%",
        "char_code": BoardChars.PERCENT,
        "description": "Partly"
    },
    "Cloudy": {
        "symbol": "O",
        "char_code": BoardChars.O,
        "description": "Cloudy"
    },
    "Overcast": {
        "symbol": "O",
        "char_code": BoardChars.O,
        "description": "Overcast"
    },
    "Rain": {
        "symbol": "/",
        "char_code": BoardChars.SLASH,
        "description": "Rain"
    },
    "Rainy": {
        "symbol": "/",
        "char_code": BoardChars.SLASH,
        "description": "Rain"
    },
    "Light Rain": {
        "symbol": "/",
        "char_code": BoardChars.SLASH,
        "description": "Lt Rain"
    },
    "Heavy Rain": {
        "symbol": "/",
        "char_code": BoardChars.SLASH,
        "description": "Hvy Rain"
    },
    "Thunderstorm": {
        "symbol": "!",
        "char_code": BoardChars.EXCLAMATION,
        "description": "Storm"
    },
    "Storm": {
        "symbol": "!",
        "char_code": BoardChars.EXCLAMATION,
        "description": "Storm"
    },
    "Snow": {
        "symbol": "O",
        "char_code": BoardChars.O,
        "description": "Snow"
    },
    "Snowy": {
        "symbol": "O",
        "char_code": BoardChars.O,
        "description": "Snow"
    },
    "Fog": {
        "symbol": "-",
        "char_code": BoardChars.DASH,
        "description": "Fog"
    },
    "Mist": {
        "symbol": "-",
        "char_code": BoardChars.DASH,
        "description": "Mist"
    },
}


def get_weather_symbol(condition: str) -> Dict[str, any]:
    """
    Get weather symbol for a condition.
    
    Args:
        condition: Weather condition string (e.g., "Clear", "Rainy")
        
    Returns:
        Dictionary with symbol, char_code, and description
    """
    # Normalize condition string
    condition = condition.strip()
    
    # Try exact match first
    if condition in WEATHER_SYMBOLS:
        return WEATHER_SYMBOLS[condition]
    
    # Try case-insensitive match
    for key, value in WEATHER_SYMBOLS.items():
        if key.lower() == condition.lower():
            return value
    
    # Try partial match (e.g., "Light Rain" contains "Rain")
    condition_lower = condition.lower()
    for key, value in WEATHER_SYMBOLS.items():
        if key.lower() in condition_lower or condition_lower in key.lower():
            return value
    
    # Default fallback
    return {
        "symbol": "?",
        "char_code": BoardChars.QUESTION,
        "description": condition[:8]  # Truncate long descriptions
    }


# Backward compatibility aliases
FiestaboardChars = BoardChars
