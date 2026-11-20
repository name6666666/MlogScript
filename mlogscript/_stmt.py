from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
import re
from ._op_table import operators, Operator, OP_TO_REF
from ._abcs import Expr, Stmt, ExprCode


class CompileError(Exception):
    pass

class Env:
    def __init__(self) -> None:
        Operator.instances = deepcopy(operators)
        self.__counter = 0
        self.funcs: dict[str, Func] = {}
        self.classes: dict[str, Class] = {}
        self.current_class = []
        self.current_func = None
        self.current_global = []
        self.objs: dict[str, str] = {}
        self.pos = None
        self.current_this = None
    
    def class_of(self, obj: str):
        if obj not in self.objs:
            raise CompileError(f'Variable {obj} is not object')
        if self.objs[obj] not in self.classes:
            raise CompileError(f'Class {self.objs[obj]} does not exists')
        return self.classes[self.objs[obj]]
    
    def counter(self):
        self.__counter += 1
        return self.__counter
    
    def get_func(self, name: str):
        if name not in self.funcs:
            raise CompileError(f'Undefined function {name}')
        return self.funcs[name]

env = Env()



class Single(Expr):
    def __init__(self, single) -> None:
        self.single = single
    
    def expr_code(self, var_name: str) -> ExprCode:
        return ExprCode([], self.single)

class Op(Expr):
    def __init__(self, op, a, b = Single('0')) -> None:
        self.op: str = op
        self.a: Expr = a
        self.b: Expr = b
    
    def expr_code(self, var_name: str) -> ExprCode:
        a, b = self.a.expr_code(f'__temp{env.counter()}'), self.b.expr_code(f'__temp{env.counter()}')
        return ExprCode(a.previous_code + b.previous_code + [f'op {OP_TO_REF[self.op]} {var_name} {a.reference} {b.reference}'], var_name)

class MlogStmt(Stmt):
    __all_stmt: dict[str, MlogStmt] = {}

    def __init__(self, format: list[str, str | None], name: str = None) -> None:
        self.__format = format
        name = name or format[0]
        self.__all_stmt[name] = self
        self.name = name
    
    @property
    def args_count(self):
        return self.__format.count(None)
    
    @classmethod
    def from_name(cls, name: str):
        return cls.__all_stmt[name]
    
    def generate(self, *args: Expr) -> list[str]:
        if len(args) != self.args_count:
            raise CompileError(f'{self.name} statement has {self.args_count} argument(s), but {len(args)} given')
        expr_codes: list[ExprCode] = [i.expr_code(f'__temp{env.counter()}') for i in args]
        copied = self.__format.copy()
        previous: list[str] = []
        for i in range(len(copied)):
            if self.__format[i] is None:
                expr_code = expr_codes.pop(0)
                copied[i] = expr_code.reference
                previous += expr_code.previous_code
        return previous + [' '.join(copied)]

class Return:
    def __init__(self, *ret_val: Expr) -> None:
        self.ret_val = ret_val

class Continue:
    pass

class Break:
    pass

@dataclass
class Label:
    label: str

@dataclass
class Goto:
    label: str

class Global:
    def __init__(self, vars) -> None:
        env.current_global.extend(vars)
        self.vars = vars

class DeferredMethodCall:
    """Defers this.method() resolution to generate() time for @override support."""
    def __init__(self, meth: str, param: list, parse_class: str):
        self.meth = meth
        self.param = param
        self.parse_class = parse_class

class DeferredStmt:
    """Defers a plain function call statement to generate() time when its args contain DeferredFuncExpr."""
    def __init__(self, func_name: str, params: list):
        self.func_name = func_name
        self.params = params

class DeferredFuncExpr(Expr):
    """Defers this.method() expression resolution for @override support."""
    def __init__(self, meth: str, param: list, parse_class: str):
        self.meth = meth
        self.param = param
        self.parse_class = parse_class
        self.func = type('DummyFunc', (), {'val_count': 0, 'check_return_count': False})()

    def _resolve(self):
        this = env.current_this
        if this and this != '$this$' and this in env.objs:
            cls = env.class_of(this)
        else:
            cls = env.classes[self.parse_class]
            this = this or '$this$'
        func = cls.get_method(self.meth, this)
        if not func.is_expr:
            raise CompileError(f'Function {func.name} has no return value, can not be use as expression')
        return func

    def expr_code(self, var_name: str) -> ExprCode:
        func = self._resolve()
        return ExprCode(func.generate(*self.param), '__return0')

pattern = re.compile(r'\%([_a-zA-Z][_a-zA-Z0-9]*)\%')
def add_prefix(prefix: str, globals: list[str], this: str = None):
    def repl(match: re.Match[str]) -> str:
        target = match.group(1)
        if '_markforattr_' in target:
            base = target.split('_markforattr_', 1)[0]
            if base == this or base in globals:
                return target
        elif target in globals:
            return target
        return prefix + target
    return repl

def _flatten(lst):
    """递归展平嵌套列表"""
    result = []
    for item in lst:
        if isinstance(item, list):
            result.extend(_flatten(item))
        else:
            result.append(item)
    return result

class Func(Stmt):
    def __init__(self, name: str, args: list[str], block: list[str]) -> None:
        self.this = None
        self.check_return_count = True
        self.name = name
        self.args = args
        self.block = _flatten(block)
        self.is_expr = any(isinstance(i, Return) for i in self.block)
        if self.is_expr:
            val_count = [len(i.ret_val) for i in self.block if isinstance(i, Return)]
            if any(i != j for i, j in zip(val_count, val_count[1:])):
                raise CompileError(f'Return values counts of function {name} are not same, use "@nocheckreturn" to pass the compilation')
            self.val_count = val_count[0]
        else:
            self.val_count = None
        if name in env.funcs:
            raise CompileError(f'Function {name} already exists')
        env.funcs[name] = self
    
    def _repl_this(self, string: str):
        if '$this$' in string and self.this is None:
            return string.replace('$this$', 'this')
        if self.this is None:
            return string
        return string.replace('$this$', self.this)
    
    def generate(self, *args: Expr) -> list[str]:
        if len(self.args) != len(args):
            raise CompileError(f'{self.name} function has {len(self.args)} argument(s), but {len(args)} given')
        init_args = [f'# calling function {self.name}']
        for param, expr in zip(self.args, args):
            init_args += MlogStmt.from_name('set').generate(Single(f'__func_{self.name}_{param}'), expr)
        label = f'__label_funcend{env.counter()}'
        block = []
        globals = []
        old_this = env.current_this
        env.current_this = self.this
        label_number = env.counter()
        for i in self.block:
            if isinstance(i, Global):
                globals.extend(i.vars)
            elif isinstance(i, Return):
                for index in range(len(i.ret_val)):
                    generated = MlogStmt.from_name('set').generate(Single(f'__return{index}'), i.ret_val[index])
                    generated = [re.sub(pattern, add_prefix(f'__func_{self.name}_', globals, self.this), self._repl_this(s)) for s in generated]
                    block.extend(generated)
                block.append(f'jump {label} always 0 0')
            elif isinstance(i, DeferredMethodCall):
                this = env.current_this
                if this and this != '$this$' and this in env.objs:
                    cls = env.class_of(this)
                else:
                    cls = env.classes[i.parse_class]
                    this = this or '$this$'
                generated = cls.get_method(i.meth, this).generate(*i.param)
                generated = [re.sub(pattern, add_prefix(f'__func_{self.name}_', globals, self.this), self._repl_this(s)) for s in generated]
                block.extend(generated)
            elif isinstance(i, DeferredStmt):
                func = env.get_func(i.func_name)
                generated = func.generate(*i.params)
                generated = [re.sub(pattern, add_prefix(f'__func_{self.name}_', globals, self.this), self._repl_this(s)) for s in generated]
                block.extend(generated)
            elif isinstance(i, Label):
                block.append(f'__func_{self.name}_{i.label}_{label_number}:')
            elif isinstance(i, Goto):
                block.append(f'jump __func_{self.name}_{i.label}_{label_number} always 0 0')
            else:
                block.append(re.sub(pattern, add_prefix(f'__func_{self.name}_', globals, self.this), self._repl_this(i)))
        env.current_this = old_this
        self.this = None
        return init_args + block + ([f'set __return{i} null' for i in range(self.val_count)] if self.is_expr and self.check_return_count else []) + [label + ':'] + [f'# end calling {self.name}']

    def to_expr(self, *args) -> Expr:
        if not self.is_expr:
            raise CompileError(f'Function {self.name} has no return value, can not be use as expression')
        ret = type('FuncExpr', (Expr,), {'expr_code': lambda s, var: ExprCode(self.generate(*args), '__return0'), 'func': self})()
        return ret

class CreateObj(Stmt):
    def __init__(self, name: str, type: str, *args: Expr) -> None:
        self.name = name
        self.type = type
        self.args = args
        env.objs[name] = type
    
    def generate(self) -> list[str]:
        try:
            return env.class_of(self.name).get_method('constructor', self.name).generate(*self.args)
        except CompileError as e:
            if e.args[0].endswith('has no method constructor'):
                return []
            raise e

class CopyObj(Stmt):
    def __init__(self, name: str, origin: str) -> None:
        self.name = name
        self.origin = origin
        if origin not in env.objs:
            raise CompileError(f'Object {origin} does not exists, can not copy')
        env.objs[name] = env.objs[origin]
    
    def generate(self) -> list[str]:
        try:
            ret = []
            for i in env.classes[env.objs[self.name]].get_attrs():
                ret.extend(MlogStmt.from_name('set').generate(Single(f'{self.name}_markforattr_{i}'), Single(f'{self.origin}_markforattr_{i}')))
            ret.extend(env.class_of(self.name).get_method('oncopy', self.name).generate())
            return ret
        except CompileError as e:
            if e.args[0].endswith('has no method oncopy'):
                return []
            raise e

class Class:
    def __init__(self, name: str, super: str = None) -> None:
        self.super = super
        self.name = name
        self.attr = []
        if name in env.classes:
            raise CompileError(f'Class {name} already exists')
        env.classes[name] = self
    
    def get_attrs(self):
        if not self.super:
            return self.attr
        return self.attr + env.classes[self.super].get_attrs()

    def get_method(self, name: str, this: str):
        ret = env.funcs.get(f'{self.name}_method_{name}')
        if not ret:
            if self.super:
                func = env.classes[self.super].get_method(name, this)
                func.this = this
                return func
            else:
                raise CompileError(f'Class {self.name} has no method {name}')
        ret.this = this
        return ret

