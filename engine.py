import secrets
import math
import time

SUITS = ['hearts', 'diamonds', 'clubs', 'spades']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
CARD_VALUES = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8,
    '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10, 'A': 11
}
DRAW_RANK_VALUES = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8,
    '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14, 'JOKER': 15
}
CUT_CARD_POSITION = 65
TURN_STARTING_CHIPS = 100
DECISION_TIMEOUT = 30
ROUND_RESULT_TIMEOUT = 5


def _secure_shuffle(lst):
    for i in range(len(lst) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        lst[i], lst[j] = lst[j], lst[i]


def create_deck(joker=False):
    deck = []
    for _ in range(2):
        for suit in SUITS:
            for rank in RANKS:
                deck.append({'rank': rank, 'suit': suit})
    if joker:
        for i in range(4):
            deck.append({'rank': 'JOKER', 'suit': 'joker'})
    _secure_shuffle(deck)
    return deck


def _is_joker_mode(game_mode):
    return game_mode in ('classic_joker', 'interactive_joker')


def _is_classic_mode(game_mode):
    return game_mode in ('classic', 'classic_joker')


def hand_value(cards):
    total = 0
    aces = 0
    jokers = 0
    for c in cards:
        if c['rank'] == 'JOKER':
            jokers += 1
            continue
        total += CARD_VALUES[c['rank']]
        if c['rank'] == 'A':
            aces += 1
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    for _ in range(jokers):
        best = 21 - total
        if best > 11:
            best = 11
        if best < 1:
            best = 1
        total += best
    return total


def is_blackjack(cards):
    return len(cards) == 2 and hand_value(cards) == 21


def _no_blackjack_after_split(hand):
    return hand.get('from_split_aces', False) or hand.get('from_split_jokers', False)


def is_ten_value(rank):
    return rank in ('10', 'J', 'Q', 'K')


def can_split(hand, chips):
    cards = hand['cards']
    if len(cards) != 2:
        return False
    r1, r2 = cards[0]['rank'], cards[1]['rank']
    same_rank = r1 == r2
    both_tens = is_ten_value(r1) and is_ten_value(r2)
    return (same_rank or both_tens) and chips >= hand['bet']


def can_double(hand, chips):
    return len(hand['cards']) == 2 and chips >= hand['bet']


def init_game_state(game_mode='classic'):
    use_joker = _is_joker_mode(game_mode)
    draw_deck = create_deck(joker=use_joker)
    state = {
        'phase': 'CARD_DRAW',
        'game_mode': game_mode,
        'draw_deck': draw_deck,
        'draw_deck_pos': 0,
        'draw_cards': {'player1': [], 'player2': []},
        'draw_winner': None,
        'chooser': None,
        'choice_made': False,
        'current_turn': 0,
        'turns': [],
        'results': {
            'player1_turn1': None,
            'player1_turn2': None,
            'player2_turn1': None,
            'player2_turn2': None,
        },
        'turn_state': None,
        'match_over': False,
        'match_result': None,
        'draw_timestamp': time.time(),
    }

    while state['draw_winner'] is None:
        state, _ = do_card_draw(state)

    return state


def do_card_draw(state):
    if state['phase'] != 'CARD_DRAW':
        return state, 'Not in card draw phase'

    game_mode = state.get('game_mode', 'classic')
    use_joker = _is_joker_mode(game_mode)
    deck = state['draw_deck']
    pos = state['draw_deck_pos']

    if pos + 2 > len(deck):
        state['draw_deck'] = create_deck(joker=use_joker)
        state['draw_deck_pos'] = 0
        deck = state['draw_deck']
        pos = 0

    card1 = deck[pos]
    card2 = deck[pos + 1]
    state['draw_deck_pos'] = pos + 2

    state['draw_cards']['player1'].append(card1)
    state['draw_cards']['player2'].append(card2)

    val1 = DRAW_RANK_VALUES.get(card1['rank'], 0)
    val2 = DRAW_RANK_VALUES.get(card2['rank'], 0)

    if val1 > val2:
        state['draw_winner'] = 1
        state['chooser'] = 1
        state['phase'] = 'CHOICE'
    elif val2 > val1:
        state['draw_winner'] = 2
        state['chooser'] = 2
        state['phase'] = 'CHOICE'
    else:
        state['draw_winner'] = None

    return state, None


def make_choice(state, chooser_goes_first_as_player):
    if state['phase'] != 'CHOICE':
        return state, 'Not in choice phase'

    chooser = state['chooser']
    other = 2 if chooser == 1 else 1

    if chooser_goes_first_as_player:
        first_player = chooser
        first_bank = other
    else:
        first_player = other
        first_bank = chooser

    state['turns'] = [
        {'player_role': first_player, 'dealer_role': first_bank},
        {'player_role': first_bank, 'dealer_role': first_player},
        {'player_role': first_bank, 'dealer_role': first_player},
        {'player_role': first_player, 'dealer_role': first_bank},
    ]
    state['choice_made'] = True
    state = enter_turn(state)
    return state, None


def enter_turn(state):
    turn_idx = state['current_turn']
    turn_info = state['turns'][turn_idx]
    player_role = turn_info['player_role']
    game_mode = state.get('game_mode', 'classic')
    use_joker = _is_joker_mode(game_mode)

    if player_role == 1:
        first_turn_result = state['results']['player1_turn1']
    else:
        first_turn_result = state['results']['player2_turn1']

    is_second_player_turn = (turn_idx >= 2 and
        ((player_role == 1 and state['results']['player1_turn1'] is not None) or
         (player_role == 2 and state['results']['player2_turn1'] is not None)))

    if is_second_player_turn and first_turn_result is not None:
        starting_chips = first_turn_result + TURN_STARTING_CHIPS
    else:
        starting_chips = TURN_STARTING_CHIPS

    state['turn_state'] = {
        'player_role': player_role,
        'dealer_role': turn_info['dealer_role'],
        'deck': create_deck(joker=use_joker),
        'cards_dealt': 0,
        'chips': starting_chips,
        'starting_chips': starting_chips,
        'cut_card_reached': False,
        'round': None,
    }
    state['phase'] = 'WAITING_BETS'
    return state


def enter_betting(state):
    state['phase'] = 'WAITING_BETS'
    state['turn_state']['round'] = None
    return state


def place_bets(state, bets):
    ts = state['turn_state']
    if state['phase'] != 'WAITING_BETS':
        return state, 'Not in betting phase'
    if not bets or len(bets) < 1 or len(bets) > 3:
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
            'hands': [{
                'cards': [], 'bet': bet_amt, 'status': 'active',
                'is_split': False, 'is_doubled': False, 'result': None,
                'from_split_aces': False, 'from_split_jokers': False,
            }],
        })

    deck = ts['deck']
    dealt = ts['cards_dealt']
    for box in boxes:
        h = box['hands'][0]
        h['cards'].append(deck[dealt]); dealt += 1
        h['cards'].append(deck[dealt]); dealt += 1

    dealer_cards = [deck[dealt], deck[dealt + 1]]
    dealt += 2
    ts['cards_dealt'] = dealt
    if dealt >= CUT_CARD_POSITION:
        ts['cut_card_reached'] = True

    insurance_per_hand = []
    for box in boxes:
        for hand in box['hands']:
            insurance_per_hand.append({
                'offered': False,
                'taken': False,
                'amount': 0,
                'decided': False,
            })

    ts['round'] = {
        'boxes': boxes,
        'dealer_cards': dealer_cards,
        'current_box': 0,
        'current_hand': 0,
        'insurance_offered': False,
        'insurance_per_hand': insurance_per_hand,
        'total_initial_bet': total_bet,
        'resolved': False,
    }

    dealer_up = dealer_cards[0]['rank']
    if dealer_up == 'A' or dealer_up == 'JOKER':
        ts['round']['insurance_offered'] = True
        for ih in ts['round']['insurance_per_hand']:
            ih['offered'] = True
        state['phase'] = 'INSURANCE'
    elif (is_ten_value(dealer_up) or dealer_up == 'JOKER') and is_blackjack(dealer_cards):
        _resolve_dealer_blackjack(state)
    else:
        _mark_player_blackjacks(ts['round'])
        state['phase'] = 'PLAYER_TURN'
        _advance_to_active(state)

    return state, None


def _resolve_dealer_blackjack(state):
    ts = state['turn_state']
    rnd = ts['round']
    for box in rnd['boxes']:
        for hand in box['hands']:
            if is_blackjack(hand['cards']) and not _no_blackjack_after_split(hand):
                ts['chips'] += hand['bet']
                hand['status'] = 'push'
                hand['result'] = 'push'
            else:
                hand['status'] = 'lose'
                hand['result'] = 'lose'
    rnd['resolved'] = True
    state['phase'] = 'ROUND_RESULT'


def _mark_player_blackjacks(rnd):
    for box in rnd['boxes']:
        for hand in box['hands']:
            if is_blackjack(hand['cards']) and not _no_blackjack_after_split(hand):
                hand['status'] = 'blackjack'


def handle_insurance(state, decisions):
    ts = state['turn_state']
    rnd = ts['round']
    if state['phase'] != 'INSURANCE':
        return state, 'Not in insurance phase'

    iph = rnd['insurance_per_hand']
    hand_idx = 0
    for box in rnd['boxes']:
        for hand in box['hands']:
            if hand_idx < len(decisions) and hand_idx < len(iph):
                take = decisions[hand_idx]
                if take and iph[hand_idx]['offered'] and not iph[hand_idx]['decided']:
                    ins_amount = math.floor(hand['bet'] / 2)
                    if ins_amount < 1:
                        ins_amount = 1
                    if ins_amount > ts['chips']:
                        ins_amount = ts['chips']
                    ts['chips'] -= ins_amount
                    iph[hand_idx]['taken'] = True
                    iph[hand_idx]['amount'] = ins_amount
                iph[hand_idx]['decided'] = True
            hand_idx += 1

    if is_blackjack(rnd['dealer_cards']):
        hand_idx = 0
        for box in rnd['boxes']:
            for hand in box['hands']:
                if hand_idx < len(iph) and iph[hand_idx]['taken']:
                    ts['chips'] += iph[hand_idx]['amount'] * 3
                if is_blackjack(hand['cards']) and not _no_blackjack_after_split(hand):
                    ts['chips'] += hand['bet']
                    hand['status'] = 'push'
                    hand['result'] = 'push'
                else:
                    hand['status'] = 'lose'
                    hand['result'] = 'lose'
                hand_idx += 1
        rnd['resolved'] = True
        state['phase'] = 'ROUND_RESULT'
    else:
        _mark_player_blackjacks(rnd)
        state['phase'] = 'PLAYER_TURN'
        _advance_to_active(state)

    return state, None


def _advance_to_active(state):
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

    box = rnd['boxes'][rnd['current_box']] if rnd['current_box'] < len(rnd['boxes']) else None
    if not box:
        return state, 'No active box'
    hand = box['hands'][rnd['current_hand']] if rnd['current_hand'] < len(box['hands']) else None
    if not hand or hand['status'] != 'active':
        return state, 'No active hand'

    deck = ts['deck']

    if action == 'hit':
        hand['cards'].append(deck[ts['cards_dealt']])
        ts['cards_dealt'] += 1
        if ts['cards_dealt'] >= CUT_CARD_POSITION:
            ts['cut_card_reached'] = True
        val = hand_value(hand['cards'])
        if val > 21:
            hand['status'] = 'bust'
            hand['result'] = None
            _next_hand(state)
        elif val == 21:
            hand['status'] = 'stand'
            _next_hand(state)

    elif action == 'stand':
        hand['status'] = 'stand'
        _next_hand(state)

    elif action == 'double':
        if not can_double(hand, ts['chips']):
            return state, 'Cannot double'
        ts['chips'] -= hand['bet']
        hand['bet'] *= 2
        hand['is_doubled'] = True
        hand['cards'].append(deck[ts['cards_dealt']])
        ts['cards_dealt'] += 1
        if ts['cards_dealt'] >= CUT_CARD_POSITION:
            ts['cut_card_reached'] = True
        if hand_value(hand['cards']) > 21:
            hand['status'] = 'bust'
        else:
            hand['status'] = 'stand'
        _next_hand(state)

    elif action == 'split':
        if not can_split(hand, ts['chips']):
            return state, 'Cannot split'
        ts['chips'] -= hand['bet']
        card1, card2 = hand['cards'][0], hand['cards'][1]
        split_aces = card1['rank'] == 'A'
        split_jokers = card1['rank'] == 'JOKER'
        hand['cards'] = [card1, deck[ts['cards_dealt']]]
        ts['cards_dealt'] += 1
        new_hand = {
            'cards': [card2, deck[ts['cards_dealt']]],
            'bet': hand['bet'], 'status': 'active',
            'is_split': True, 'is_doubled': False, 'result': None,
            'from_split_aces': split_aces or hand.get('from_split_aces', False),
            'from_split_jokers': split_jokers or hand.get('from_split_jokers', False),
        }
        ts['cards_dealt'] += 1
        hand['is_split'] = True
        hand['from_split_aces'] = split_aces or hand.get('from_split_aces', False)
        hand['from_split_jokers'] = split_jokers or hand.get('from_split_jokers', False)
        if ts['cards_dealt'] >= CUT_CARD_POSITION:
            ts['cut_card_reached'] = True
        box['hands'].insert(rnd['current_hand'] + 1, new_hand)
    else:
        return state, f'Unknown action: {action}'

    return state, None


def _next_hand(state):
    ts = state['turn_state']
    rnd = ts['round']
    rnd['current_hand'] += 1
    box = rnd['boxes'][rnd['current_box']]
    while rnd['current_hand'] < len(box['hands']):
        hand = box['hands'][rnd['current_hand']]
        if hand['status'] == 'active':
            if hand_value(hand['cards']) == 21:
                hand['status'] = 'stand'
                rnd['current_hand'] += 1
                continue
            return
        rnd['current_hand'] += 1
    rnd['current_box'] += 1
    rnd['current_hand'] = 0
    _advance_to_active(state)


def _play_dealer(state):
    ts = state['turn_state']
    rnd = ts['round']
    dc = rnd['dealer_cards']
    game_mode = state.get('game_mode', 'classic')

    any_standing = any(
        h['status'] in ('stand', 'blackjack')
        for box in rnd['boxes'] for h in box['hands']
    )

    if not any_standing:
        _resolve_hands(state)
        return

    if _is_classic_mode(game_mode):
        deck = ts['deck']
        while hand_value(dc) < 17:
            dc.append(deck[ts['cards_dealt']])
            ts['cards_dealt'] += 1
            if ts['cards_dealt'] >= CUT_CARD_POSITION:
                ts['cut_card_reached'] = True
        _resolve_hands(state)
    else:
        dealer_val = hand_value(dc)
        if dealer_val <= 20:
            state['phase'] = 'DEALER_TURN'
            return
        _resolve_hands(state)


def dealer_action(state, action):
    if state['phase'] != 'DEALER_TURN':
        return state, 'Not in dealer turn phase'

    ts = state['turn_state']
    rnd = ts['round']
    deck = ts['deck']
    dc = rnd['dealer_cards']

    if action == 'stand':
        _resolve_hands(state)
        return state, None
    elif action == 'hit':
        dc.append(deck[ts['cards_dealt']])
        ts['cards_dealt'] += 1
        if ts['cards_dealt'] >= CUT_CARD_POSITION:
            ts['cut_card_reached'] = True

        dealer_val = hand_value(dc)
        if dealer_val > 21 or dealer_val == 21:
            _resolve_hands(state)
            return state, None

        state['phase'] = 'DEALER_TURN'
        return state, None
    else:
        return state, f'Unknown dealer action: {action}'


def _resolve_hands(state):
    ts = state['turn_state']
    rnd = ts['round']
    dc = rnd['dealer_cards']

    dealer_val = hand_value(dc)
    dealer_bust = dealer_val > 21
    dealer_bj = is_blackjack(dc)

    for box in rnd['boxes']:
        for hand in box['hands']:
            if hand['status'] == 'bust':
                hand['result'] = 'lose'
            elif hand['status'] == 'blackjack':
                if dealer_bj:
                    ts['chips'] += hand['bet']
                    hand['result'] = 'push'
                else:
                    ts['chips'] += hand['bet'] + math.floor(3 * hand['bet'] / 2)
                    hand['result'] = 'blackjack_win'
            elif hand['status'] == 'stand':
                pval = hand_value(hand['cards'])
                if dealer_bust or pval > dealer_val:
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


def next_round_or_end_turn(state):
    ts = state['turn_state']
    if ts['cut_card_reached'] or ts['chips'] <= 0:
        return end_turn(state)
    enter_betting(state)
    return state, False


def end_turn(state):
    ts = state['turn_state']
    turn_chips = ts['chips']
    turn_idx = state['current_turn']
    player_role = state['turns'][turn_idx]['player_role']

    if player_role == 1:
        if state['results']['player1_turn1'] is None:
            state['results']['player1_turn1'] = turn_chips
        else:
            state['results']['player1_turn2'] = turn_chips
    else:
        if state['results']['player2_turn1'] is None:
            state['results']['player2_turn1'] = turn_chips
        else:
            state['results']['player2_turn2'] = turn_chips

    state['current_turn'] += 1

    if state['current_turn'] >= 4:
        state['match_over'] = True
        p1 = state['results']['player1_turn2'] if state['results']['player1_turn2'] is not None else (state['results']['player1_turn1'] or 0)
        p2 = state['results']['player2_turn2'] if state['results']['player2_turn2'] is not None else (state['results']['player2_turn1'] or 0)
        if p1 > p2:
            winner = 1
        elif p2 > p1:
            winner = 2
        else:
            winner = 0
        state['match_result'] = {
            'player1_total': p1,
            'player2_total': p2,
            'winner': winner,
        }
        state['phase'] = 'MATCH_OVER'
        return state, True

    state['turn_state'] = None
    state = enter_turn(state)
    return state, False


def check_timeout(match):
    if not match.is_waiting_decision or not match.decision_started_at:
        return False
    timeout = ROUND_RESULT_TIMEOUT if match.decision_type == 'NEXT' else DECISION_TIMEOUT
    return (time.time() - match.decision_started_at) > timeout


def apply_timeout(state, match):
    phase = state['phase']
    ts = state.get('turn_state')

    if phase == 'CARD_DRAW':
        match.is_waiting_decision = False
        return state, False

    elif phase == 'CHOICE':
        state, _ = make_choice(state, True)
        match.is_waiting_decision = False
        return state, True

    elif phase == 'WAITING_BETS':
        if ts and ts['chips'] > 0:
            state, _ = place_bets(state, [1])
        else:
            state, _ = end_turn(state)
        match.is_waiting_decision = False
        return state, True

    elif phase == 'INSURANCE':
        num_hands = sum(len(box['hands']) for box in ts['round']['boxes'])
        state, _ = handle_insurance(state, [False] * num_hands)
        match.is_waiting_decision = False
        return state, True

    elif phase == 'PLAYER_TURN':
        state, _ = player_action(state, 'stand')
        match.is_waiting_decision = False
        return state, True

    elif phase == 'DEALER_TURN':
        state, _ = dealer_action(state, 'stand')
        match.is_waiting_decision = False
        return state, True

    elif phase == 'ROUND_RESULT':
        state, _ = next_round_or_end_turn(state)
        match.is_waiting_decision = False
        return state, True

    return state, False


def set_decision_timer(match, decision_type):
    match.decision_started_at = time.time()
    match.decision_type = decision_type
    match.is_waiting_decision = True


def clear_decision_timer(match):
    match.decision_started_at = None
    match.decision_type = None
    match.is_waiting_decision = False


def get_timer_remaining(match):
    if not match.is_waiting_decision or not match.decision_started_at:
        return None
    timeout = ROUND_RESULT_TIMEOUT if match.decision_type == 'NEXT' else DECISION_TIMEOUT
    remaining = timeout - (time.time() - match.decision_started_at)
    return max(0, remaining)


def get_client_state(state, user_player_num, match=None, spectator=False):
    cs = {
        'current_turn': state['current_turn'],
        'phase': state['phase'],
        'results': state['results'],
        'match_over': state['match_over'],
        'match_result': state['match_result'],
        'total_turns': 4,
        'draw_cards': state.get('draw_cards'),
        'draw_winner': state.get('draw_winner'),
        'chooser': state.get('chooser'),
        'choice_made': state.get('choice_made', False),
        'draw_timestamp': state.get('draw_timestamp'),
        'game_mode': state.get('game_mode', 'classic'),
    }

    if match:
        cs['timer_remaining'] = get_timer_remaining(match)
        cs['decision_type'] = match.decision_type

    if state.get('turns') and state['current_turn'] < len(state['turns']):
        ti = state['turns'][state['current_turn']]
        cs['current_player_role'] = ti['player_role']
        cs['current_dealer_role'] = ti['dealer_role']
        if spectator:
            cs['i_am_dealer'] = False
            cs['is_my_turn'] = False
            cs['is_dealer_turn'] = state['phase'] == 'DEALER_TURN'
        elif state['phase'] == 'DEALER_TURN':
            cs['i_am_dealer'] = (ti['dealer_role'] == user_player_num)
            cs['is_my_turn'] = (ti['dealer_role'] == user_player_num)
            cs['is_dealer_turn'] = True
        elif state['phase'] in ('CARD_DRAW', 'CHOICE'):
            cs['i_am_dealer'] = (ti['dealer_role'] == user_player_num)
            if state['phase'] == 'CHOICE':
                cs['is_my_turn'] = (state['chooser'] == user_player_num)
            else:
                cs['is_my_turn'] = True
            cs['is_dealer_turn'] = False
        else:
            cs['i_am_dealer'] = (ti['dealer_role'] == user_player_num)
            cs['is_my_turn'] = (ti['player_role'] == user_player_num)
            cs['is_dealer_turn'] = False
    elif state['phase'] in ('CARD_DRAW', 'CHOICE'):
        cs['i_am_dealer'] = False
        cs['is_my_turn'] = True
        cs['is_dealer_turn'] = False

    ts = state.get('turn_state')
    if ts:
        cs['chips'] = ts['chips']
        cs['starting_chips'] = ts['starting_chips']
    if ts and ts.get('round'):
        rnd = ts['round']
        cs['cut_card_reached'] = ts['cut_card_reached']
        cs['round'] = {
            'boxes': [],
            'dealer_cards': [],
            'current_box': rnd['current_box'],
            'current_hand': rnd['current_hand'],
            'insurance_offered': rnd['insurance_offered'],
            'resolved': rnd['resolved'],
        }
        show_all_dealer = rnd['resolved'] or state['phase'] == 'DEALER_TURN'
        is_dealer = False
        if state.get('turns') and state['current_turn'] < len(state['turns']):
            ti = state['turns'][state['current_turn']]
            is_dealer = (ti['dealer_role'] == user_player_num) and not spectator

        if show_all_dealer or is_dealer:
            cs['round']['dealer_cards'] = rnd['dealer_cards']
        else:
            cs['round']['dealer_cards'] = [rnd['dealer_cards'][0], {'rank': '?', 'suit': '?'}]

        cs['round']['dealer_value'] = hand_value(rnd['dealer_cards']) if (show_all_dealer or is_dealer) else hand_value([rnd['dealer_cards'][0]])

        for box in rnd['boxes']:
            box_data = {'hands': []}
            for hand in box['hands']:
                hand_data = {
                    'cards': hand['cards'],
                    'bet': hand['bet'],
                    'status': hand['status'],
                    'result': hand['result'],
                    'is_split': hand.get('is_split', False),
                    'is_doubled': hand.get('is_doubled', False),
                    'value': hand_value(hand['cards']),
                    'can_split': can_split(hand, ts['chips']) if hand['status'] == 'active' else False,
                    'can_double': can_double(hand, ts['chips']) if hand['status'] == 'active' else False,
                }
                box_data['hands'].append(hand_data)
            cs['round']['boxes'].append(box_data)

    return cs
