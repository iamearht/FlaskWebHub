"""
Game state and player state management for Royal 21.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set
from card import Card, Deck
from hand import Hand


class Phase(Enum):
    """Game phases."""
    SETUP = "setup"
    PREFLOP = "preflop"
    DRAW = "draw"
    RIVER = "river"
    SHOWDOWN = "showdown"
    HAND_OVER = "hand_over"


class ActionType(Enum):
    """Action types available to players."""
    ESCROW_ADD = "escrow_add"
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    STAND = "stand"
    HIT = "hit"
    DOUBLE = "double"
    SPLIT = "split"


@dataclass
class PlayerState:
    """State of a player in the game."""
    seat_index: int
    username: str
    stack: int  # Total chips available
    in_hand: bool = True  # Is player still in this hand?

    # Chip circles
    normal_circle: int = 0  # Main pot
    escrow_circle: int = 0  # Side pot

    # Cards and reveals
    hole_cards: List[Card] = field(default_factory=list)
    revealed_card: Optional[Card] = None  # First revealed card (from first preflop action)

    # Split hands
    split_hands: Dict[str, Hand] = field(default_factory=dict)  # "split_a", "split_b", etc.
    original_hand: Optional[Hand] = None

    # State flags
    hit_taken: bool = False  # If true, cannot add escrow on river (escrow-lock)
    folded: bool = False
    all_in: bool = False

    def __post_init__(self):
        if self.original_hand is None:
            self.original_hand = Hand(self.hole_cards, "original")

    def total_chips_on_table(self) -> int:
        """Total chips committed this hand."""
        return self.normal_circle + self.escrow_circle

    def chips_remaining(self) -> int:
        """Chips still in player's stack (not on table)."""
        return self.stack - self.total_chips_on_table()

    def can_bet(self, amount: int) -> bool:
        """Can player commit this amount from their stack?"""
        return amount <= self.chips_remaining()


@dataclass
class GameState:
    """Complete game state."""
    game_id: str
    num_players: int
    small_blind: int = 1  # Antes/posts
    big_blind: int = 1
    button_index: int = 0
    deck: Optional[Deck] = None

    # Player states
    players: List[PlayerState] = field(default_factory=list)

    # Current hand
    phase: Phase = Phase.SETUP
    current_action_index: int = 0  # Which player's turn
    action_count: int = 0  # Actions taken in current phase

    # Betting state
    current_highest_normal: int = 0  # Highest normal circle bet
    current_highest_bet_from: Optional[int] = None  # Which player made highest bet
    min_raise_amount: int = 0

    # Pot totals (calculated)
    normal_pot: int = 0
    escrow_pot: int = 0

    # Action log
    logs: List[str] = field(default_factory=list)

    def active_players(self) -> List[PlayerState]:
        """Get players still in the hand."""
        return [p for p in self.players if p.in_hand and not p.folded]

    def active_seats(self) -> List[int]:
        """Get seat indices of active players."""
        return [p.seat_index for p in self.active_players()]

    def num_active(self) -> int:
        """Number of players still in hand."""
        return len(self.active_players())

    def table_total(self) -> int:
        """
        Calculate TABLE_TOTAL: sum of all active players' normal + escrow circles.
        Used for custom pot-limit sizing.
        """
        total = 0
        for player in self.active_players():
            total += player.normal_circle + player.escrow_circle
        return total

    def next_active_index(self, from_index: int) -> Optional[int]:
        """
        Get the next active player's index starting from 'from_index' (clockwise).
        Returns None if only one or fewer active players.
        """
        active = self.active_seats()
        if len(active) <= 1:
            return None

        # Find next seat clockwise from from_index
        start_pos = active.index(from_index) if from_index in active else 0
        for i in range(1, len(active)):
            idx = (start_pos + i) % len(active)
            return active[idx]

        return None

    def get_player(self, seat_index: int) -> Optional[PlayerState]:
        """Get player by seat index."""
        for p in self.players:
            if p.seat_index == seat_index:
                return p
        return None

    def log_action(self, message: str):
        """Log an action."""
        self.logs.append(message)

    def reset_hand(self):
        """Reset for new hand (called after hand_over)."""
        # Move button
        self.button_index = (self.button_index + 1) % self.num_players

        # Reset player states
        for player in self.players:
            player.in_hand = True
            player.folded = False
            player.hit_taken = False
            player.normal_circle = 0
            player.escrow_circle = 0
            player.hole_cards = []
            player.revealed_card = None
            player.split_hands = {}
            player.original_hand = None
            player.all_in = False

        # Reset game state
        self.phase = Phase.SETUP
        self.current_action_index = 0
        self.action_count = 0
        self.current_highest_normal = 0
        self.current_highest_bet_from = None
        self.normal_pot = 0
        self.escrow_pot = 0
        self.logs = []

        # Reset deck
        if self.deck:
            self.deck.reset()
