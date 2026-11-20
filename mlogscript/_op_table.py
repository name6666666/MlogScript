
LEVEL: list[list[str]] = []
OP_TO_REF: dict[str, str] = {}

class Operator:
    instances: list['Operator'] = []
    def __init__(self, op: str, ref: str, lev: int) -> None:
        self.op = op
        self.ref = ref
        self.lev = lev
    
    def __repr__(self):
        return f'Operator({self.op}, {self.ref}, {self.lev})'

    @classmethod
    def refresh(cls):
        op: dict[int, list[str]] = {}
        for i in cls.instances:
            if i.lev in op:
                op[i.lev].append(i.op)
            else:
                op[i.lev] = [i.op]
        lst = list(op.items())
        lst.sort(key=lambda t: t[0])
        LEVEL.clear()
        for t in lst:
            LEVEL.append(t[1])
        OP_TO_REF.clear()
        for i in cls.instances:
            OP_TO_REF[i.op] = i.ref


operators = [
    # Level 0: exponentiation
    Operator('**', 'pow', 0),
    # Level 1: multiplicative
    Operator('*', 'mul', 1),
    Operator('/', 'div', 1),
    Operator('//', 'idiv', 1),
    Operator('%', 'mod', 1),
    Operator('%%', 'emod', 1),
    # Level 2: additive
    Operator('+', 'add', 2),
    Operator('-', 'sub', 2),
    # Level 3: comparison
    Operator('==', 'equal', 3),
    Operator('!=', 'notEqual', 3),
    Operator('<', 'lessThan', 3),
    Operator('>', 'greaterThan', 3),
    Operator('<=', 'lessThanEq', 3),
    Operator('>=', 'greaterThanEq', 3),
    Operator('===', 'strictEqual', 3),
    # Level 4: logical
    Operator('&&', 'land', 4),
    # Bitwise
    Operator('<<', 'shl', 1),
    Operator('>>', 'shr', 1),
    Operator('>>>', 'ushr', 1),
    Operator('&', 'and', 4),
    Operator('|', 'or', 4),
    Operator('^', 'xor', 4),
]
