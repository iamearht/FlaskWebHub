"""Action types and definitions."""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class ActionType(str, Enum):
    """Types of player actions."""
    # Betting round actions
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"

    # Draw phase actions
    DRAW = "draw"
    STAND = "stand"

    # Reveal action (first action in BETTING_1)
    REVEAL = "reveal"  # Choose which card to reveal


@dataclass
class Action:
    """Represents a player action."""
    action_type: ActionType
    seat: int
    amount: Optional[int] = None  # For BET, RAISE, DRAW
    card_index: Optional[int] = None  # For REVEAL (0 or 1)

    def __str__(self) -> str:
        if self.action_type in (ActionType.BET, ActionType.RAISE):
            return f"{self.action_type.value} {self.amount}"
        elif self.action_type == ActionType.DRAW:
            return f"draw"
        elif self.action_type == ActionType.REVEAL:
            return f"reveal card {self.card_index}"
        else:
            return self.action_type.value
