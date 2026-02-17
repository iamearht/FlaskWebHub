import random
import math

SUITS = ['hearts', 'diamonds', 'clubs', 'spades']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
CARD_VALUES = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8,
    '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10, 'A': 11
}
CUT_CARD_POSITION = 65
TURN_STARTING_CHIPS = 100

def create_deck():
    deck = []
    for _ in range(2):
        for suit in SUITS:
            for rank in RANKS:
                deck.append({'rank': rank, 'suit': suit})
    random.shuffle(deck)
    return deck

def hand_value(cards):
    total = 0
    aces = 0
    for c in cards:
        val = CARD_VALUES[c['rank']]
        total += val
        if c['rank'] == 'A':
            aces += 1
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total

def is_blackjack(cards):
    return len(cards) == 2 and hand_value(cards) == 21

def is_ten_value(rank):
    return rank in ('10', 'J', 'Q', 'K')

def can_split(hand, chips, box_bet):
    cards = hand['cards']
    if len(cards) != 2:
        return False
    if hand.get('is_split'):
        return False
    r1, r2 = cards[0]['rank'], cards[1]['rank']
    same_rank = (r1 == r2) or (is_ten_value(r1) and is_ten_value(r2))
    return same_rank and chips >= box_bet

def can_double(hand, chips, box_bet):
    cards = hand['cards']
    if len(cards) != 2:
        return False
    return chips >= box_bet

def init_game_state():
    return {
        'current_turn': 0,
        'turns_order': [
            {'player_role': 1, 'dealer_role': 2},
            {'player_role': 2, 'dealer_role': 1},
            {'player_role': 1, 'dealer_role': 2},
            {'player_role': 2, 'dealer_role': 1},
        ],
        'results': {
            'player1': [],
            'player2': [],
        },
        'turn_state': None,
        'phase': 'TURN_START',
        'match_over': False,
        'match_result': None,
    }

def start_turn(state):
    turn_info = state['turns_order'][state['current_turn']]
    state['turn_state'] = {
        'player_role': turn_info['player_role'],
        'dealer_role': turn_info['dealer_role'],
        'deck': create_deck(),
        'cards_dealt': 0,
        'chips': TURN_STARTING_CHIPS,
        'cut_card_reached': False,
        'round': None,
    }
    state['phase'] = 'WAITING_BETS'
    return state

def place_bets(state, bets):
    ts = state['turn_state']
    if state['phase'] != 'WAITING_BETS':
        return state, 'Not in betting phase'

    if not bets or len(bets) == 0 or len(bets) > 3:
        return state, 'Must place 1-3 bets'

    total_bet = 0
    valid_bets = []
    for b in bets:
        amt = int(b)
        if amt < 1:
            return state, 'Minimum bet per box is 1'
        total_bet += amt
        valid_bets.append(amt)

    if total_bet > ts['chips']:
        return state, 'Total bet exceeds available chips'

    ts['chips'] -= total_bet

    boxes = []
    for bet_amt in valid_bets:
        boxes.append({
            'bet': bet_amt,
            'hands': [{'cards': [], 'bet': bet_amt, 'status': 'active', 'is_split': False, 'is_doubled': False}],
        })

    deck = ts['deck']
    dealt = ts['cards_dealt']

    for box in boxes:
        hand = box['hands'][0]
        hand['cards'].append(deck[dealt]); dealt += 1
        hand['cards'].append(deck[dealt]); dealt += 1

    dealer_cards = [deck[dealt], deck[dealt + 1]]
    dealt += 2

    ts['cards_dealt'] = dealt
    if dealt >= CUT_CARD_POSITION:
        ts['cut_card_reached'] = True

    ts['round'] = {
        'boxes': boxes,
        'dealer_cards': dealer_cards,
        'current_box': 0,
        'current_hand': 0,
        'insurance_offered': False,
        'insurance_taken': False,
        'insurance_amount': 0,
        'total_initial_bet': total_bet,
        'resolved': False,
    }

    if dealer_cards[0]['rank'] == 'A':
        state['phase'] = 'INSURANCE'
        ts['round']['insurance_offered'] = True
    else:
        if _check_dealer_blackjack_no_ace(ts['round'], dealer_cards):
            _resolve_round(state)
        else:
            _check_player_blackjacks(ts['round'])
            state['phase'] = 'PLAYER_TURN'
            _advance_to_active_hand(state)

    return state, None

def _check_dealer_blackjack_no_ace(rnd, dealer_cards):
    if is_blackjack(dealer_cards) and is_ten_value(dealer_cards[0]['rank']):
        return True
    return False

def _check_player_blackjacks(rnd):
    for box in rnd['boxes']:
        for hand in box['hands']:
            if is_blackjack(hand['cards']) and not hand.get('is_split'):
                hand['status'] = 'blackjack'

def handle_insurance(state, take_insurance):
    ts = state['turn_state']
    rnd = ts['round']

    if state['phase'] != 'INSURANCE':
        return state, 'Not in insurance phase'

    if take_insurance:
        ins_amount = math.floor(rnd['total_initial_bet'] / 2)
        if ins_amount > ts['chips']:
            ins_amount = ts['chips']
        ts['chips'] -= ins_amount
        rnd['insurance_taken'] = True
        rnd['insurance_amount'] = ins_amount

    dealer_cards = rnd['dealer_cards']
    if is_blackjack(dealer_cards):
        if rnd['insurance_taken']:
            ts['chips'] += rnd['insurance_amount'] * 3

        for box in rnd['boxes']:
            for hand in box['hands']:
                if is_blackjack(hand['cards']):
                    ts['chips'] += hand['bet']
                    hand['status'] = 'push'
                else:
                    hand['status'] = 'lose'

        rnd['resolved'] = True
        state['phase'] = 'ROUND_RESULT'
    else:
        _check_player_blackjacks(rnd)
        state['phase'] = 'PLAYER_TURN'
        _advance_to_active_hand(state)

    return state, None

def _advance_to_active_hand(state):
    ts = state['turn_state']
    rnd = ts['round']

    while rnd['current_box'] < len(rnd['boxes']):
        box = rnd['boxes'][rnd['current_box']]
        while rnd['current_hand'] < len(box['hands']):
            hand = box['hands'][rnd['current_hand']]
            if hand['status'] == 'active':
                return
            rnd['current_hand'] += 1
        rnd['current_box'] += 1
        rnd['current_hand'] = 0

    _play_dealer(state)

def player_action(state, action):
    ts = state['turn_state']
    rnd = ts['round']

    if state['phase'] != 'PLAYER_TURN':
        return state, 'Not in player turn phase'

    if rnd['current_box'] >= len(rnd['boxes']):
        return state, 'No active hand'

    box = rnd['boxes'][rnd['current_box']]
    if rnd['current_hand'] >= len(box['hands']):
        return state, 'No active hand in box'

    hand = box['hands'][rnd['current_hand']]
    if hand['status'] != 'active':
        return state, 'Hand is not active'

    deck = ts['deck']

    if action == 'hit':
        hand['cards'].append(deck[ts['cards_dealt']])
        ts['cards_dealt'] += 1
        if ts['cards_dealt'] >= CUT_CARD_POSITION:
            ts['cut_card_reached'] = True
        val = hand_value(hand['cards'])
        if val > 21:
            hand['status'] = 'bust'
            _move_next_hand(state)
        elif val == 21:
            hand['status'] = 'stand'
            _move_next_hand(state)

    elif action == 'stand':
        hand['status'] = 'stand'
        _move_next_hand(state)

    elif action == 'double':
        if not can_double(hand, ts['chips'], hand['bet']):
            return state, 'Cannot double'
        ts['chips'] -= hand['bet']
        hand['bet'] *= 2
        hand['is_doubled'] = True
        hand['cards'].append(deck[ts['cards_dealt']])
        ts['cards_dealt'] += 1
        if ts['cards_dealt'] >= CUT_CARD_POSITION:
            ts['cut_card_reached'] = True
        val = hand_value(hand['cards'])
        if val > 21:
            hand['status'] = 'bust'
        else:
            hand['status'] = 'stand'
        _move_next_hand(state)

    elif action == 'split':
        if not can_split(hand, ts['chips'], hand['bet']):
            return state, 'Cannot split'
        ts['chips'] -= hand['bet']
        card1 = hand['cards'][0]
        card2 = hand['cards'][1]

        hand['cards'] = [card1, deck[ts['cards_dealt']]]
        ts['cards_dealt'] += 1
        new_hand = {
            'cards': [card2, deck[ts['cards_dealt']]],
            'bet': hand['bet'],
            'status': 'active',
            'is_split': True,
            'is_doubled': False,
        }
        ts['cards_dealt'] += 1
        hand['is_split'] = True

        if ts['cards_dealt'] >= CUT_CARD_POSITION:
            ts['cut_card_reached'] = True

        box['hands'].insert(rnd['current_hand'] + 1, new_hand)

        val = hand_value(hand['cards'])
        if val == 21:
            hand['status'] = 'stand'
            _move_next_hand(state)

    else:
        return state, f'Unknown action: {action}'

    return state, None

def _move_next_hand(state):
    ts = state['turn_state']
    rnd = ts['round']

    rnd['current_hand'] += 1
    box = rnd['boxes'][rnd['current_box']]
    while rnd['current_hand'] < len(box['hands']):
        hand = box['hands'][rnd['current_hand']]
        if hand['status'] == 'active':
            val = hand_value(hand['cards'])
            if val == 21:
                hand['status'] = 'stand'
                rnd['current_hand'] += 1
                continue
            return
        rnd['current_hand'] += 1

    rnd['current_box'] += 1
    rnd['current_hand'] = 0
    _advance_to_active_hand(state)

def _play_dealer(state):
    ts = state['turn_state']
    rnd = ts['round']
    deck = ts['deck']
    dealer_cards = rnd['dealer_cards']

    any_standing = False
    for box in rnd['boxes']:
        for hand in box['hands']:
            if hand['status'] in ('stand', 'blackjack'):
                any_standing = True

    if any_standing:
        while hand_value(dealer_cards) < 17:
            dealer_cards.append(deck[ts['cards_dealt']])
            ts['cards_dealt'] += 1
            if ts['cards_dealt'] >= CUT_CARD_POSITION:
                ts['cut_card_reached'] = True

    dealer_val = hand_value(dealer_cards)
    dealer_bj = is_blackjack(dealer_cards)
    dealer_bust = dealer_val > 21

    for box in rnd['boxes']:
        for hand in box['hands']:
            if hand['status'] == 'bust':
                continue
            elif hand['status'] == 'blackjack':
                if dealer_bj:
                    ts['chips'] += hand['bet']
                    hand['result'] = 'push'
                else:
                    payout = hand['bet'] + math.floor(3 * hand['bet'] / 2)
                    ts['chips'] += payout
                    hand['result'] = 'blackjack_win'
            elif hand['status'] == 'stand':
                pval = hand_value(hand['cards'])
                if dealer_bust:
                    ts['chips'] += hand['bet'] * 2
                    hand['result'] = 'win'
                elif pval > dealer_val:
                    ts['chips'] += hand['bet'] * 2
                    hand['result'] = 'win'
                elif pval == dealer_val:
                    ts['chips'] += hand['bet']
                    hand['result'] = 'push'
                else:
                    hand['result'] = 'lose'
            else:
                hand['result'] = 'lose'

    rnd['resolved'] = True
    state['phase'] = 'ROUND_RESULT'

def _resolve_round(state):
    ts = state['turn_state']
    rnd = ts['round']
    dealer_cards = rnd['dealer_cards']
    dealer_bj = is_blackjack(dealer_cards)

    for box in rnd['boxes']:
        for hand in box['hands']:
            if is_blackjack(hand['cards']) and not hand.get('is_split'):
                ts['chips'] += hand['bet']
                hand['status'] = 'push'
                hand['result'] = 'push'
            else:
                hand['status'] = 'lose'
                hand['result'] = 'lose'

    rnd['resolved'] = True
    state['phase'] = 'ROUND_RESULT'

def next_round_or_end_turn(state):
    ts = state['turn_state']

    if ts['cut_card_reached'] or ts['chips'] <= 0:
        return end_turn(state)

    ts['round'] = None
    state['phase'] = 'WAITING_BETS'
    return state, False

def end_turn(state):
    ts = state['turn_state']
    turn_chips = ts['chips']
    turn_idx = state['current_turn']
    turn_info = state['turns_order'][turn_idx]

    if turn_info['player_role'] == 1:
        state['results']['player1'].append(turn_chips)
    else:
        state['results']['player2'].append(turn_chips)

    state['current_turn'] += 1

    if state['current_turn'] >= 4:
        state['match_over'] = True
        p1_total = sum(state['results']['player1'])
        p2_total = sum(state['results']['player2'])
        state['match_result'] = {
            'player1_total': p1_total,
            'player2_total': p2_total,
        }
        if p1_total > p2_total:
            state['match_result']['winner'] = 1
        elif p2_total > p1_total:
            state['match_result']['winner'] = 2
        else:
            state['match_result']['winner'] = 0
        state['phase'] = 'MATCH_OVER'
        return state, True

    state['turn_state'] = None
    state['phase'] = 'TURN_START'
    return state, False

def get_client_state(state, user_player_num):
    cs = {
        'current_turn': state['current_turn'],
        'phase': state['phase'],
        'results': state['results'],
        'match_over': state['match_over'],
        'match_result': state['match_result'],
    }

    if state.get('turns_order') and state['current_turn'] < 4:
        ti = state['turns_order'][state['current_turn']]
        cs['current_player_role'] = ti['player_role']
        cs['current_dealer_role'] = ti['dealer_role']
        cs['is_my_turn'] = (ti['player_role'] == user_player_num)
    else:
        cs['is_my_turn'] = False

    ts = state.get('turn_state')
    if ts:
        cs['chips'] = ts['chips']
        cs['cut_card_reached'] = ts['cut_card_reached']

        rnd = ts.get('round')
        if rnd:
            cs['round'] = {
                'boxes': [],
                'dealer_cards': [],
                'current_box': rnd['current_box'],
                'current_hand': rnd['current_hand'],
                'insurance_offered': rnd['insurance_offered'],
                'insurance_taken': rnd['insurance_taken'],
                'resolved': rnd['resolved'],
            }

            for box in rnd['boxes']:
                b = {'hands': []}
                for hand in box['hands']:
                    h = {
                        'cards': hand['cards'],
                        'bet': hand['bet'],
                        'status': hand['status'],
                        'is_split': hand.get('is_split', False),
                        'is_doubled': hand.get('is_doubled', False),
                        'value': hand_value(hand['cards']),
                        'result': hand.get('result'),
                    }

                    if hand['status'] == 'active':
                        h['can_split'] = can_split(hand, ts['chips'], hand['bet'])
                        h['can_double'] = can_double(hand, ts['chips'], hand['bet'])
                    else:
                        h['can_split'] = False
                        h['can_double'] = False

                    b['hands'].append(h)
                cs['round']['boxes'].append(b)

            dc = rnd['dealer_cards']
            if rnd['resolved']:
                cs['round']['dealer_cards'] = dc
                cs['round']['dealer_value'] = hand_value(dc)
            else:
                cs['round']['dealer_cards'] = [dc[0], {'rank': '?', 'suit': '?'}]
                cs['round']['dealer_value'] = CARD_VALUES.get(dc[0]['rank'], 0)
    else:
        cs['chips'] = None

    return cs
