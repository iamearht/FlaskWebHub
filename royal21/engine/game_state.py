"""Game state management."""

from dataclasses import dataclass, field
from typing import Dict, Optional, TYPE_CHECKING
from .deck import Deck

if TYPE_CHECKING:
    from .card import Card


@dataclass
class PlayerState:
    """Represents a player in the game."""

    seat: int
    name: str
    player_id: str
    stack: int

    # Hand tracking
    hole_cards: list = field(default_factory=list)  # [Card, Card] for current hand

    # Betting state
    chips_in_pot: int = 0  # Total chips contributed this hand
    current_bet: int = 0  # Chips bet in current round
    is_folded: bool = False  # Player has folded
    is_all_in: bool = False  # Player is all-in (no chips left)
    is_active: bool = True  # Still in the hand (not folded)

    # Card reveal state (PREFLOP mechanic)
    exposed_card_index: Optional[int] = None  # Which card (0 or 1) was revealed, or None if not yet revealed
    has_acted_preflop: bool = False  # Tracks if player has taken an action in PREFLOP

    # Betting round action tracking
    has_acted_on_current_bet: bool = False  # Tracks if player has acted on the current bet level in betting round

    # Draw phase state
    is_bust: bool = False  # True if hand value exceeds 21

    def calculate_hand_value(self) -> int:
        """Calculate hand value using blackjack rules with Ace optimization.

        Cards are valued 2-10 (face), J/Q/K=10, A=11.
        Aces are counted as 1 if needed to avoid busting (going over 21).
        """
        if not self.hole_cards:
            return 0

        # Sum all cards (Aces counted as 11 initially)
        total = sum(card.value for card in self.hole_cards)

        # Count Aces in hand
        ace_count = sum(1 for card in self.hole_cards if card.rank == "A")

        # Convert Aces from 11 to 1 as needed to minimize bust
        while total > 21 and ace_count > 0:
            total -= 10  # Convert one Ace from 11 to 1 (difference of 10)
            ace_count -= 1

        return total

    def check_bust(self) -> bool:
        """Check if hand exceeds 21 and update is_bust flag."""
        if self.calculate_hand_value() > 21:
            self.is_bust = True
            return True
        return False


@dataclass
class Pot:
    """Represents the pot(s) in the current hand."""

    main_pot: int = 0  # Main pot chips
    side_pots: list[dict] = field(default_factory=list)  # Side pots if all-ins occurred; each: {"amount": int, "eligible_seats": list[int]}


@dataclass
class GameState:
    """Represents the overall game state."""

    # EXISTING: Core state
    button_seat: Optional[int] = None
    players: Dict[int, PlayerState] = field(default_factory=dict)
    deck: Deck = field(default_factory=Deck)

    # NEW: Phase tracking
    phase: str = "ANTES"  # ANTES, DEAL, BETTING_1, DRAW, BETTING_2, SHOWDOWN
    hand_number: int = 0

    # NEW: Betting state
    pot: Pot = field(default_factory=Pot)
    current_actor: Optional[int] = None  # Seat of player to act
    current_high_bet: int = 0  # Max bet this round (big blind initially)
    button_big_blind: int = 0  # The big blind amount (button's second ante)

    def add_player(self, seat: int, name: str, player_id: str, stack: int):
        """Add a player to the game."""
        self.players[seat] = PlayerState(
            seat=seat,
            name=name,
            player_id=player_id,
            stack=stack
        )

    def get_seated_players(self) -> list[int]:
        """Return list of seat numbers with players."""
        return sorted(self.players.keys())

    def get_player_name(self, seat: int) -> str:
        """Get player name for a seat."""
        return self.players[seat].name if seat in self.players else "Unknown"

    def get_active_players(self) -> list[int]:
        """Return list of seats with players still in hand (not folded)."""
        return [
            seat for seat, player in self.players.items()
            if player and not player.is_folded and player.is_active
        ]

    def get_next_actor_after(self, seat: int) -> Optional[int]:
        """Find next seated, active, non-folded player (wraps at 6→0)."""
        for offset in range(1, 7):
            check_seat = (seat + offset) % 7
            if check_seat in self.players:
                player = self.players[check_seat]
                if player and not player.is_folded and player.is_active:
                    return check_seat
        return None

    def reset_for_new_hand(self) -> None:
        """Reset player betting state for new hand."""
        for player in self.players.values():
            player.hole_cards = []
            player.chips_in_pot = 0
            player.current_bet = 0
            player.is_folded = False
            player.is_all_in = False
            player.is_active = True
            player.exposed_card_index = None
            player.has_acted_preflop = False
            player.is_bust = False

        self.pot = Pot()
        self.current_actor = None
        self.current_high_bet = 0
        self.button_big_blind = 0
        self.hand_number += 1
