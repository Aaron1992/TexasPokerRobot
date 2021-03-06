import sys
import socket
import re
import time
import traceback

import card_probability
import cards2_judge as decision
from card import Card
from player import Player

# card parameter
hand_cards = [None]*2
board_cards = []
probability = [None]*10

# state
board_state = ''
round_state = 0

# key is player's PID
num_player = 0
opponent_dic = {}

# money and bet information
my_money = [0]*2
all_money = [0]*2
my_bet_history = []

# my PID
client_pid = ''

# game over flag
is_game_over = False

# blind flag
blind_flag = 0

# parse socket command_block
def update_player_from_seat(lines):
    global opponent_dic
    global is_game_over
    global num_player
    global my_money
    global all_money
    global blind_flag
    global my_bet_history
    my_bet_history = []
    num_player = 0
    my_money = [0]*2
    all_money = [0]*2

    for line in lines:
        parameter = line.split(' ')
        try:
            pid = parameter[-4]
            jetton = int(parameter[-3])
            money = int(parameter[-2])
            if pid != client_pid:
                num_player += 1
                all_money[0] += jetton
                all_money[1] += money
                if pid in opponent_dic:
                    opponent_dic[pid].reset_bet_and_action()
                else:
                    opponent_dic[pid] = Player()
            else:
                if parameter[1] == 'blind':
                    blind_flag = 1
                else:
                    blind_flag = 0
                my_money[0] = jetton
                my_money[1] = money
        except:
            is_game_over = True
            print 'seat parse error'

    for pid in opponent_dic:
        oppo = opponent_dic[pid]
        if oppo.is_game_over is False:
            if oppo.bet != []:
                oppo.turn_to_game_over()

def update_player_from_showdown(lines):
    global opponent_dic
    global is_game_over
    global is_first_round
    is_first_round = True

    for line in lines[7:]:
        try:
            pid = line.split(' ')[1]
            if pid != client_pid:
                opponent_dic[pid].update_from_showdown(line, board_cards)
                print 'card_strength_history:'
                print opponent_dic[pid].card_strength_history
        except:
            is_game_over = True
            print 'showdown parse error'

def update_player_from_inquire(lines):
    global opponent_dic
    global is_game_over

    for line in lines[:-1]:
        parameter = line.split(' ')
        pid = parameter[0]
        try:
            if pid != client_pid:
                opponent_dic[pid].update_from_inquire(line)
            else:
                if len(my_bet_history) > 0:
                    delta = int(parameter[3]) - sum(my_bet_history)
                    my_bet_history.append(delta)
                else:
                    my_bet_history.append(int(parameter[3]))
        except:
            is_game_over = True
            print 'inquire parse error'

def card_parse(lines):
    cards = []

    for line in lines:
        parameter = line.split(' ')
        try:
            card_str = str(Card(parameter[0], parameter[1]))
            cards.append(card_str)
        except:
            global is_game_over
            is_game_over = True
            print 'card parse error'

    if len(cards) == 1:
        return card_str
    return cards

def card_update(command, body):
    global board_state
    board_state = command

    global round_state
    round_state = 0

    global board_cards
    global probability
    if command == 'hold':
        global hand_cards
        hand_cards = card_parse(body)
    elif command == 'flop':
        board_cards = card_parse(body)
        probability = card_probability.calc(hand_cards, board_cards)
    elif command == 'turn':
        board_cards.append(card_parse(body))
        probability = card_probability.calc(hand_cards, board_cards)
    elif command == 'river':
        board_cards.append(card_parse(body))

def creat_oppo_array():
    oppobehave = []
    opponum = 0
    for key in opponent_dic:
        oppo = opponent_dic[key]
        if oppo.state != []:
            oppobehave.append(oppo.state)
            if oppo.is_game_over is False:
                opponum += oppo.bet

    return oppobehave, opponum

def creat_oppo_history_array():
    playermovement = []
    playerrank = []
    card_player = []
    for key in opponent_dic:
        oppo = opponent_dic[key]
        playerrank.append(oppo.card_strength_history)
        playermovement.append(oppo.action_count_history)
        card_player.append(oppo.card_history)

    return playermovement, playerrank, card_player

def make_decision():
    global round_state
    round_state += 1
    (oppobehave, opponum) = creat_oppo_array()
    (playermovement, playerrank, card_player) = creat_oppo_history_array()

    action = None

    '''
    if error occurs return "check"
    '''
    if board_state == 'hold':
        card = hand_cards + [None]*7
        try:
            action = decision.makeDecisionBlindFinal(card, round_state, oppobehave, opponum, num_player, playermovement, card_player, playerrank, my_money, all_money,blind_flag)
        except:
            print 'blind decision error'
            action = 'check'
    elif board_state == 'flop':
        card = hand_cards + board_cards + [None]*2
        try:
            action = decision.makeDecisionFlopFinal(card,round_state,probability,oppobehave,opponum,num_player,playermovement,playerrank,my_money,all_money,my_bet_history)
        except:
            print 'my_bet_history',my_bet_history
            print 'flop decision error'
            action = 'check'
    elif board_state == 'turn':
        card = hand_cards + board_cards + [None]
        try:
            action = decision.makeDecisionTurnFinal(card,round_state,probability,oppobehave,opponum,num_player,playermovement,playerrank,my_money,all_money,my_bet_history)
        except:
            print 'my_bet_history',my_bet_history

            print 'turn decision error'
            action = 'check'
    elif board_state == 'river':
        card = hand_cards + board_cards
        # try:
        action =decision.makeDecisionRiverFinal(card,round_state,oppobehave,opponum,num_player,playermovement,playerrank,my_money,all_money,my_bet_history)
        # except:
        #     print 'my_bet_history',my_bet_history

        #     print 'river decision error'
        #     action = 'check'

    print 'board_state is ', board_state
    print 'send message to server: %s\n' % action
    return action

def parse_with_recv(recv):
    command_block = re.finditer(r"(\w+)/ \n([\s\S]*?)/(\1) \n", recv)

    for block in command_block:
        command = block.group(1)
        body = block.group(2).splitlines()

        if command == 'inquire':
            update_player_from_inquire(body)
            return make_decision()
        elif command == 'showdown':
            update_player_from_showdown(body)
        elif command == 'seat':
            update_player_from_seat(body)
        elif command in ['hold','flop','turn','river']:
            card_update(command, body)

    return None

def run(argv):

    global client_pid

    # parameter init
    server_ip = argv[0]
    server_port = int(argv[1])
    client_ip = argv[2]
    client_port = int(argv[3])
    client_pid = argv[4]

    # register to gameserver
    while True:
        try:
            clientsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            clientsocket.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE)
            clientsocket.bind((client_ip, client_port))
            clientsocket.connect((server_ip, server_port))
            print 'connect to server success'
            reg_message = 'reg: ' + client_pid + ' ' + 'yutian' + ' \n'
            print 'send register message: ' + reg_message
            clientsocket.send(reg_message)
            break
        except socket.error, (value, message):
            print 'connect error: ' + message
            print 'try to reconnect in 1 seconds'
            time.sleep(1.0)
            continue

    while not is_game_over :
        try:
            recv = clientsocket.recv(1024)
            if len(recv) > 0:
                print 'recv is:\n---------------\n' + recv
                if recv == 'game-over \n':
                    break
                else:
                    result = parse_with_recv(recv)
                    if result is not None:
                        clientsocket.send(result)
            else:
                break

        except socket.error, (value, message):
            print "rec err: " + message
            break

    clientsocket.close()
    print '\n------------\nconnection closed and GAME OVER\n------------'

if __name__ == '__main__':
    run(sys.argv[1:])
