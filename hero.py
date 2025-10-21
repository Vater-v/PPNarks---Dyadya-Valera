from enum import Enum

class HeroState(Enum):
    UNDEFINED = 0         # Не определён, наблюдает, ход противника
    CAN_ROLL_OR_DOUBLE = 1  # Может бросить кости или предложить дабл
    CAN_MOVE_CHECKERS = 2   # Может двигать шашки
    CAN_COMMIT_TURN = 3     # Может подтвердить ход
    CAN_ANSWER_DOUBLE = 4   # Может подтвердить double
    HINTS_SENT_THIS_TURN_ref: list[int]

