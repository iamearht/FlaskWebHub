"""
Royal 21 in-memory game manager.
Holds SeatingManager and optional GameEngine per table (keyed by table DB id).
"""
from typing import Dict, Optional

from royal21.tables.seating import SeatingManager
from royal21.engine.game_engine import GameEngine


class TableState:
    """All runtime state for one Royal 21 table."""

    def __init__(self, table_id: int, ante: int, min_buyin: int, max_buyin: int):
        self.table_id = table_id
        self.ante = ante
        self.min_buyin = min_buyin
        self.max_buyin = max_buyin
        self.seating = SeatingManager(max_seats=7)
        self.engine: Optional[GameEngine] = None

        # Which seated players have clicked "ready" for the current hand
        self.ready_seats: set = set()
        # Which seats have acted in the current DRAW phase (for phase-complete detection)
        self.draw_acted_seats: set = set()
        # Map player_id (str) → socket SID for targeted emits
        self.player_sids: Dict[str, str] = {}

        self.hand_number: int = 0

    # ------------------------------------------------------------------
    # Seat helpers
    # ------------------------------------------------------------------
    def get_player_seat(self, player_id) -> Optional[int]:
        pid = str(player_id)
        for seat_num, seat in self.seating.seats.items():
            if seat.player_id is not None and str(seat.player_id) == pid:
                return seat_num
        return None

    def get_available_seats(self) -> list:
        return [i for i in range(7) if self.seating.seats[i].player_id is None]

    def all_seated_ready(self) -> bool:
        occupied = set(self.seating.get_occupied_seats())
        return len(occupied) >= 2 and occupied.issubset(self.ready_seats) and self.ready_seats.issubset(occupied)

    # ------------------------------------------------------------------
    # Engine lifecycle
    # ------------------------------------------------------------------
    def create_engine(self) -> GameEngine:
        self.hand_number += 1
        self.draw_acted_seats = set()
        self.engine = GameEngine(
            table_id=str(self.table_id),
            game_id=str(self.hand_number),
            ante=self.ante,
            seating=self.seating,
        )
        return self.engine

    def sync_stacks_to_seating(self):
        """After a hand ends, copy engine stacks back to the SeatingManager."""
        if not self.engine:
            return
        for seat_num, player in self.engine.state.players.items():
            seat_obj = self.seating.seats.get(seat_num)
            if seat_obj:
                seat_obj.stack = player.stack

    # ------------------------------------------------------------------
    # SID tracking
    # ------------------------------------------------------------------
    def add_player_sid(self, player_id, sid: str):
        self.player_sids[str(player_id)] = sid

    def remove_player_sid(self, player_id):
        self.player_sids.pop(str(player_id), None)


# ---------------------------------------------------------------------------
# Module-level store
# ---------------------------------------------------------------------------
_tables: Dict[int, TableState] = {}


def get_table(table_id: int) -> Optional[TableState]:
    return _tables.get(table_id)


def get_or_create_table(table_id: int, ante: int, min_buyin: int, max_buyin: int) -> TableState:
    if table_id not in _tables:
        _tables[table_id] = TableState(table_id, ante, min_buyin, max_buyin)
    return _tables[table_id]


def remove_table(table_id: int) -> None:
    _tables.pop(table_id, None)


def all_table_ids() -> list:
    return list(_tables.keys())
