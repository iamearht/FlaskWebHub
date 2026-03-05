"""
Royal 21 Configuration and Game Constants

Customize these settings for game variants and rules.
"""

# ============================================================================
# GAME RULES
# ============================================================================

# Number of players
MIN_PLAYERS = 2
MAX_PLAYERS = 7
DEFAULT_PLAYERS = 7

# Starting stacks (big blinds)
MIN_STARTING_STACK = 50
DEFAULT_STARTING_STACK = 200

# Blinds structure
SMALL_BLIND = 1
BIG_BLIND = 1
ANTE_ESCROW = 1  # Escrow ante (per player)
BUTTON_POST_NORMAL = 1  # Button posts to normal circle

# Betting constraints
MIN_BET = 1  # Minimum bet size
MAX_RAISE_CAP_ENABLED = True  # Use custom pot-limit (max_raise_to = current_high + table_total)

# Draw phase rules
ALLOW_RESPLIT = False  # Allow re-splitting (e.g., split aces into 4 hands)
ALLOW_DOUBLE_AFTER_SPLIT = False  # Allow doubling on split hands
NATURAL_BLACKJACK_STANDS = True  # Natural blackjack must stand (cannot hit)

# River betting restrictions
HIT_TRIGGERS_ESCROW_LOCK = True  # If player hit, cannot add escrow on river
DOUBLE_TRIGGERS_ESCROW_LOCK = False  # Double down doesn't lock escrow

# Showdown logic
USE_SPLIT_HAND_HALF_POTS = True  # True = two half-pots; False = alternative logic
USE_LAYERED_ESCROW = True  # True = side-pot logic; False = simple escrow split

# ============================================================================
# GAME PHASES
# ============================================================================

PHASES = {
    "SETUP": 0,
    "PREFLOP": 1,
    "DRAW": 2,
    "RIVER": 3,
    "SHOWDOWN": 4,
    "HAND_OVER": 5,
}

# ============================================================================
# HAND RANKINGS
# ============================================================================

# Blackjack hand rankings (higher number = better)
HAND_VALUES = {
    "BUST": 0,
    "TWENTY": 20,
    "NINETEEN": 19,
    "EIGHTEEN": 18,
    "SEVENTEEN": 17,
    "SIXTEEN": 16,
    "FIFTEEN": 15,
    "FOURTEEN": 14,
    "THIRTEEN": 13,
    "TWELVE": 12,
    "ELEVEN": 11,
    "TEN": 10,
    "NATURAL_BLACKJACK": 999,  # Special value for natural blackjack
}

# Ten-value card rankings for blackjack tiebreaker
# Higher = better (K > Q > J > 10)
TEN_VALUE_RANKS = {
    "KING": 4,
    "QUEEN": 3,
    "JACK": 2,
    "TEN": 1,
}

# ============================================================================
# CARD DECK
# ============================================================================

DECK_SIZE = 52
SUITS = ["HEARTS", "DIAMONDS", "CLUBS", "SPADES"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

# ============================================================================
# UI / FRONTEND
# ============================================================================

# Color scheme (poker-inspired)
THEME_COLORS = {
    "bg": "#0d1b2a",
    "bg_light": "#1a2f45",
    "table": "#1a4d2e",
    "primary": "#ff6b35",  # Orange
    "success": "#4ecdc4",  # Teal (escrow)
    "danger": "#e63946",   # Red (fold)
    "text": "#f0f0f0",
    "text_dim": "#999",
}

# Seat visualization
SEATS_PER_ROW = 7
SEAT_SIZE = "140px"

# Action panel settings
SHOW_LEGAL_ACTIONS = True
SHOW_CHIP_BREAKDOWN = True
SHOW_POT_DISPLAY = True
SHOW_ACTION_LOG = True

# ============================================================================
# SERVER
# ============================================================================

# FastAPI settings
HOST = "0.0.0.0"
PORT = 8000
DEBUG = True

# WebSocket settings
WS_HEARTBEAT_INTERVAL = 30  # seconds
WS_HEARTBEAT_TIMEOUT = 10  # seconds

# In-memory storage limits (before cleanup)
MAX_CONCURRENT_GAMES = 100
GAME_CLEANUP_TIMEOUT = 3600  # seconds (1 hour)

# ============================================================================
# LOGGING
# ============================================================================

LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# ============================================================================
# TESTING
# ============================================================================

# Deterministic seed for reproducible games
ENABLE_SEEDED_GAMES = True
DEFAULT_SEED = 42

# Test configuration
TEST_PLAYER_COUNT = 2
TEST_STARTING_STACK = 1000
TEST_TIMEOUT = 10  # seconds

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_default_game_config():
    """Get default configuration for a new game."""
    return {
        "num_players": DEFAULT_PLAYERS,
        "starting_stack": DEFAULT_STARTING_STACK,
        "small_blind": SMALL_BLIND,
        "big_blind": BIG_BLIND,
        "min_bet": MIN_BET,
        "allow_resplit": ALLOW_RESPLIT,
        "allow_double_after_split": ALLOW_DOUBLE_AFTER_SPLIT,
    }


def validate_game_config(config):
    """Validate game configuration."""
    errors = []

    if not MIN_PLAYERS <= config.get("num_players", 0) <= MAX_PLAYERS:
        errors.append(f"Players must be between {MIN_PLAYERS} and {MAX_PLAYERS}")

    if config.get("starting_stack", 0) < MIN_STARTING_STACK:
        errors.append(f"Starting stack must be at least {MIN_STARTING_STACK}")

    if config.get("min_bet", 0) < 1:
        errors.append("Minimum bet must be at least 1")

    return errors


# ============================================================================
# EXAMPLE: HOW TO USE
# ============================================================================

"""
In your game code:

from config import (
    DEFAULT_PLAYERS,
    DEFAULT_STARTING_STACK,
    HAND_VALUES,
    MAX_RAISE_CAP_ENABLED,
    HIT_TRIGGERS_ESCROW_LOCK,
)

# Create a game with defaults
game_config = get_default_game_config()

# Validate custom config
custom_config = {
    "num_players": 5,
    "starting_stack": 300,
}
errors = validate_game_config(custom_config)
if errors:
    print("Invalid config:", errors)
else:
    # Use the config
    print(f"Starting {custom_config['num_players']} player game")

# Use constants in logic
if HIT_TRIGGERS_ESCROW_LOCK:
    # Enforce escrow-lock rule
    player.can_add_escrow = False
"""
