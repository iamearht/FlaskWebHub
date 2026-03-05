# Royal 21 - Game Flow Diagram

## High-Level Game Flow

```
┌──────────────────────────────────────────────────────┐
│               GAME INITIALIZATION                     │
│  1. Create game (2-7 players)                        │
│  2. Set starting stacks                              │
│  3. Randomize button position                        │
└─────────────────────┬──────────────────────────────┘
                      │
                      ↓
        ╔═════════════════════════════════════╗
        ║        LOOP: HAND SEQUENCE          ║
        ║  (Repeats until game ends)          ║
        ╚═════════════────────════════════════╝
                      │
                      ↓
        ┌──────────────────────────────┐
        │  PHASE 0: SETUP              │
        │  └─ Collect antes/posts      │
        │  └─ Deal 2 cards per player  │
        │  └─ Clear chip circles       │
        │  └─ Set action order         │
        └─────────────┬────────────────┘
                      │
                      ↓
        ┌──────────────────────────────────────────┐
        │  PHASE 1: PREFLOP BETTING               │
        │  (Two-step turns for each player)        │
        │  Step A: Escrow add (optional)           │
        │  Step B: Fold/Check/Bet/Call/Raise     │
        │                                          │
        │  Special: REVEAL RULE on first action   │
        │  (Player must reveal 1 hole card)       │
        │                                          │
        │  Loop until:                            │
        │  - All active players matched bet, OR   │
        │  - Only 1 player remains                │
        └─────────────┬───────────────────────────┘
                      │
              ┌───────┴────────┐
              │                │
           YES│                │NO
             1|                └─→ [SHOWDOWN] ──→ [HAND END]
        Player  (2+ players)
        Remains?
              │
              ↓
        ┌──────────────────────────────────────────┐
        │  PHASE 2: DRAW                           │
        │  (Players draw cards to improve hand)    │
        │                                          │
        │  For each active player:                │
        │  Choose: STAND / HIT / DOUBLE / SPLIT  │
        │                                          │
        │  - STAND: Take no more cards            │
        │  - HIT: Draw 1+ cards (sets escrow lock)│
        │  - DOUBLE: Draw exactly 1 card          │
        │  - SPLIT: Split into 2 hands             │
        │           (only if cards same rank)     │
        │                                          │
        │  Natural blackjack must STAND           │
        └─────────────┬───────────────────────────┘
                      │
                      ↓
        ┌──────────────────────────────────────────┐
        │  PHASE 3: RIVER BETTING                  │
        │  (Second betting round)                  │
        │                                          │
        │  Same as PREFLOP, but:                  │
        │  - Cannot add escrow if HIT in draw     │
        │  - Use updated pot totals               │
        │                                          │
        │  Loop until:                            │
        │  - All active players matched bet, OR   │
        │  - Only 1 player remains                │
        └─────────────┬───────────────────────────┘
                      │
                      ↓
        ┌────────────────────────────────────────────┐
        │  PHASE 4: SHOWDOWN                         │
        │  (Evaluate hands and distribute pots)      │
        │                                            │
        │  1. Evaluate all hands using ranking:     │
        │     Natural Blackjack > 21 > 20 > ... > BUST │
        │                                            │
        │  2. Determine winners (main pot):         │
        │     - If no splits: Best hand wins        │
        │     - If splits: Divide into A/B halves   │
        │                                            │
        │  3. Determine winners (escrow pot):       │
        │     - Layered side-pot logic              │
        │     - Capped by each player's escrow      │
        │                                            │
        │  4. Distribute chips to winners           │
        │                                            │
        │  5. Update player stacks                  │
        └─────────────┬────────────────────────────┘
                      │
                      ↓
        ┌──────────────────────────────────┐
        │  PHASE 5: HAND END               │
        │  └─ Move button clockwise        │
        │  └─ Reset player states          │
        │  └─ Ready for next hand          │
        └─────────────┬────────────────────┘
                      │
                      └──→ [Loop back to SETUP for next hand]
```

## Detailed: PREFLOP BETTING ROUND

```
PREFLOP BETTING ROUND
═════════════════════════════════════════════════════════════

Starting:
- current_highest_normal_bet = 1 (button's post)
- current_highest_escrow = 1 (all antes)
- Action order: Left of button, clockwise

For each active player (in order):

┌─────────────────────────────────────────┐
│  TURN: Player's Action                  │
├─────────────────────────────────────────┤
│                                         │
│  Is this player's FIRST action?         │
│  ├─ YES: Show REVEAL RULE               │
│  │   "Choose which hole card to reveal" │
│  │   [Card 1] or [Card 2]               │
│  │                                     │
│  └─ NO: Skip reveal rule                │
│                                         │
│  STEP A: ESCROW STEP (if not locked)    │
│  ├─ Optional: Add to escrow circle     │
│  │   Input: 0 to remaining_stack chips │
│  │   Effect: Increases TABLE_TOTAL      │
│  └─ If hit in draw: Escrow locked       │
│                                         │
│  STEP B: NORMAL BETTING STEP            │
│  ├─ If current_high = your_normal:     │
│  │   (you're matched)                  │
│  │   Options: CHECK or BET             │
│  │                                     │
│  │   CHECK: Do nothing, move to next   │
│  │   BET: Set normal_circle to amount   │
│  │        amount ∈ [1, TABLE_TOTAL]    │
│  │                                     │
│  └─ If current_high > your_normal:     │
│     (you're facing a bet)              │
│     Options: FOLD, CALL, or RAISE      │
│                                         │
│     FOLD: Exit hand, forfeit chips     │
│     CALL: Match current_high           │
│            cost = current_high - your_normal │
│     RAISE: Raise to new_amount          │
│              new_amount ∈                │
│              [current_high,             │
│               current_high + TABLE_TOTAL] │
│                                         │
└─────────────────────────────────────────┘
                  ↓
            Update state:
            - current_highest_normal = new highest
            - TABLE_TOTAL = recalculate
            - Move to next player

REPEAT for all players until:
────────────────────────────────────────
✓ All remaining players have matched current_highest_normal
  (everyone called the highest bet)

✓ OR only 1 player remains (others folded)

Then → [PHASE 2: DRAW]
```

## Detailed: DRAW PHASE

```
DRAW PHASE - PLAYER TURN
═════════════════════════════════════════════════════════════

Player sees their 2 hole cards and chooses:

If cards are identical in rank:
┌─────────────────────────────────────────────┐
│  OPTION: SPLIT                              │
│  ├─ Creates Hand A: [Card 1]               │
│  ├─ Creates Hand B: [Card 2]               │
│  ├─ Deal 1 card to each hand               │
│  ├─ Play Hand A first (HIT/STAND/DOUBLE)  │
│  ├─ Then play Hand B (HIT/STAND/DOUBLE)   │
│  └─ Normal circle doubled (split bets)    │
└─────────────────────────────────────────────┘
            ↓
      Play Hand A first

If total == 21 (natural blackjack):
┌─────────────────────────────────────────────┐
│  NATURAL BLACKJACK: MUST STAND              │
│  └─ Cannot hit, cannot double               │
│  └─ Auto-moves to next hand/player          │
└─────────────────────────────────────────────┘
            ↓
      Move to next player

Otherwise:
┌─────────────────────────────────────────────┐
│  CHOOSE ACTION:                             │
│                                             │
│  [STAND] - Take no more cards               │
│  └─ Ends this hand's draw phase            │
│  └─ Move to next hand or next player       │
│                                             │
│  [HIT] - Draw 1 card                        │
│  ├─ Card added to hand                     │
│  ├─ Flag: hit_taken = TRUE (escrow lock)   │
│  ├─ New total calculated                   │
│  │                                         │
│  └─ If total > 21 (BUST):                  │
│     └─ Auto-stand this hand                │
│     └─ Move to next hand or player         │
│                                             │
│  └─ If total ≤ 21:                         │
│     └─ Offer action again (HIT/STAND)     │
│                                             │
│  [DOUBLE] - Draw exactly 1 card, then stand │
│  ├─ Can only double before hitting          │
│  ├─ Normal circle doubled (bet doubled)    │
│  ├─ Draw 1 card                            │
│  ├─ Auto-stand (cannot hit further)        │
│  └─ Does NOT set escrow_lock               │
│                                             │
└─────────────────────────────────────────────┘
            ↓
     All players drawn
            ↓
    [PHASE 3: RIVER BETTING]
```

## Detailed: RIVER BETTING ROUND

```
RIVER BETTING ROUND
═════════════════════════════════════════════════════════════

Similar to PREFLOP, but with RESTRICTIONS:

┌─────────────────────────────────────────┐
│  STEP A: ESCROW STEP (WITH RESTRICTION) │
├─────────────────────────────────────────┤
│                                         │
│  Did player HIT in draw phase?          │
│  ├─ YES: ESCROW LOCKED                 │
│  │   └─ Cannot add escrow!              │
│  │   └─ Escrow already in circle stays  │
│  │                                     │
│  └─ NO: Can add escrow                 │
│      └─ Same as preflop                │
│      └─ Input: 0 to remaining_stack    │
│                                         │
└─────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────┐
│  STEP B: NORMAL BETTING STEP            │
├─────────────────────────────────────────┤
│  (Identical to PREFLOP)                 │
│                                         │
│  ├─ If matched: CHECK or BET           │
│  ├─ If facing bet: FOLD, CALL, RAISE   │
│  └─ Rules same as preflop               │
│                                         │
└─────────────────────────────────────────┘
            ↓
      All players acted
            ↓
    [PHASE 4: SHOWDOWN]
```

## Detailed: SHOWDOWN EVALUATION

```
SHOWDOWN
═════════════════════════════════════════════════════════════

All remaining (non-folded) players reveal hands:

1. EVALUATE HAND RANKINGS
   ────────────────────────────────────
   For each hand:
   - Blackjack total (≤21 best, >21 bust)
   - Natural Blackjack? (A + 10-value only)

   Ranking:
   1. Natural Blackjack (999)
   2. 21 (non-natural)
   3. 20
   4. 19
   ...
   Lowest non-bust

   Ties within rank:
   - Natural blackjacks: K > Q > J > 10 (ten-value rank)
   - Same ten-rank: Suited beats offsuit
   - Still tied: Split pot equally

2. MAIN POT SETTLEMENT
   ───────────────────

   IF no players split:
   └─ Best hand wins entire main_pot

   IF one or more players split:
   ├─ Divide main_pot into A and B halves
   │  main_pot_A = floor(main_pot / 2)
   │  main_pot_B = main_pot - main_pot_A
   │
   ├─ For each split player:
   │  ├─ Hand A competes in pot_A only
   │  └─ Hand B competes in pot_B only
   │
   ├─ For each non-split player:
   │  ├─ Their hand competes in BOTH halves
   │  └─ If ties: wins share of that half
   │
   └─ Determine winners of each half
      └─ Distribute pot_A and pot_B

3. ESCROW POT SETTLEMENT (Simplified)
   ──────────────────────────────────

   Using layered side-pot logic:

   ├─ Sort active players by escrow amount
   ├─ Create layers:
   │  └─ Each layer covers players with escrow ≥ threshold
   │
   ├─ If splits present:
   │  ├─ Divide escrow_pot into A/B halves
   │  ├─ Split each player's escrow: A and B portions
   │  └─ Award each half separately
   │
   └─ Award each layer/half to best hand

4. TOTAL PAYOUTS
   ──────────────

   Player.stack += main_pot_winnings
   Player.stack += escrow_pot_winnings

   For folded players:
   └─ No change (chips already forfeited)

5. DISPLAY RESULTS
   ────────────────

   Show to all players:
   ├─ All hands revealed
   ├─ Rankings
   ├─ Winners and amounts
   ├─ Updated stacks
   └─ Button position for next hand

                  ↓
            [PHASE 5: HAND END]
```

## Action Decision Tree

```
╔════════════════════════════════════════════════════════════════╗
║                    YOUR TURN DECISION TREE                     ║
╚════════════════════════════════════════════════════════════════╝

START: Your turn to act
  │
  ├─ PHASE = PREFLOP or RIVER?
  │  │
  │  ├─ YES: Go to BETTING DECISION
  │  └─ NO: Go to DRAW DECISION
  │
  ├─────────────────────────────────────────────────────────────┐
  │ BETTING DECISION (PREFLOP or RIVER)                        │
  ├─────────────────────────────────────────────────────────────┤
  │ Step 1: ADD ESCROW (optional)                              │
  │         [Escrow input] [Add Escrow] or [Skip]              │
  │                                                             │
  │ Step 2: CHOOSE NORMAL BET ACTION                           │
  │         │                                                  │
  │         ├─ current_high > my_normal?                       │
  │         │  │                                               │
  │         │  ├─ YES: I'm facing a bet                        │
  │         │  │  ├─ FOLD (exit hand)                          │
  │         │  │  ├─ CALL (match current_high)                 │
  │         │  │  └─ RAISE (raise_to = amount)                 │
  │         │  │       where amount ≤ current_high + TABLE_TOTAL│
  │         │  │                                               │
  │         │  └─ NO: Everyone's matched                       │
  │         │     ├─ CHECK (do nothing)                        │
  │         │     └─ BET (set normal_circle to amount)         │
  │         │         where amount ≤ TABLE_TOTAL              │
  │                                                             │
  └─────────────────────────────────────────────────────────────┘
  │
  ├─────────────────────────────────────────────────────────────┐
  │ DRAW DECISION (PHASE 2 - DRAW)                             │
  ├─────────────────────────────────────────────────────────────┤
  │                                                              │
  │ Check my hand total:                                        │
  │ │                                                           │
  │ ├─ IS NATURAL BLACKJACK (A + 10-value)?                    │
  │ │  └─ YES: MUST STAND (auto-resolved)                      │
  │ │                                                           │
  │ ├─ SAME RANK CARDS (e.g., 8♠ + 8♦)?                        │
  │ │  └─ YES: Can SPLIT                                       │
  │ │         ├─ [SPLIT] → Creates 2 hands                     │
  │ │         │            Play Hand A, then Hand B            │
  │ │         ├─ [HIT]   → Draw 1+ cards (sets escrow-lock)    │
  │ │         ├─ [STAND] → Take no more                        │
  │ │         └─ [DOUBLE] → Draw 1 card, then stand           │
  │ │                                                           │
  │ └─ NO SPLIT OPTION:                                        │
  │    ├─ [HIT]   → Draw 1+ cards (sets escrow-lock)           │
  │    ├─ [STAND] → Take no more                               │
  │    └─ [DOUBLE] → Draw 1 card, then stand                  │
  │                                                              │
  └─────────────────────────────────────────────────────────────┘
  │
  └─→ SEND ACTION TO SERVER
      ↓
      SERVER UPDATES GAME STATE
      ↓
      BROADCAST TO ALL PLAYERS
      ↓
      NEXT PLAYER'S TURN
```

## Betting Rules Quick Reference

```
TABLE_TOTAL Calculation:
─────────────────────────
TABLE_TOTAL = sum(all active players' normal circles)
            + sum(all active players' escrow circles)

Used for: max_raise_to calculation

Max Raise Calculation:
──────────────────────
If facing a bet:
  max_raise_to = current_highest_normal + TABLE_TOTAL

If no bet yet:
  max_bet = TABLE_TOTAL

Examples:
─────────
Current high = $10
Player stacks: P1 has 5 normal + 3 escrow, P2 has 8 normal + 2 escrow
TABLE_TOTAL = (10 + 5 + 8) + (0 + 3 + 2) = 28

Max raise = $10 + $28 = $38 (vs current $10 bet)

All-In Rules:
─────────────
If player has < required amount:
  └─ Go all-in with remaining chips
  └─ Create side pot for excess from other players

Escrow-Lock Rules:
──────────────────
On RIVER betting:
  If player took HIT in draw phase:
    └─ Cannot add escrow
    └─ Can still bet/raise normal circle
    └─ Existing escrow stays live

  If player ONLY stood/doubled/split (no hit):
    └─ CAN add escrow
```

---

This flow diagram covers all phases, decision points, and rules comprehensively.
For detailed rules, see [README.md](README.md)
