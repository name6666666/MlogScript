from ast import literal_eval
import io
import json
from pathlib import Path
import sys
from lark.exceptions import VisitError, UnexpectedInput
from importlib.resources import files
from lark import Lark, Transformer, Token
import pyperclip
from .._op_table import LEVEL
from .._stmt import *
from ._preprocessor import MyPreprocessor


grammer = files('mlogscript._parse').joinpath('grammer.lark').read_text('utf-8')

def merge_op(op_lst: list, target_op: list[str]) -> list | None:
    for i in range(len(op_lst)):
        if op_lst[i] in target_op:
            part = op_lst[i - 1: i + 2]
            replacement = Op(part[1], part[0], part[2])
            return op_lst[:i - 1] + [replacement] + op_lst[i + 2:]
    return None

class Trans(Transformer):
    @staticmethod
    def _flatten(lst):
        """递归展平嵌套列表"""
        result = []
        for item in lst:
            if isinstance(item, list):
                result.extend(Trans._flatten(item))
            else:
                result.append(item)
        return result

    def start(self, args):
        stmts = sum(args, [])
        stmts = [re.sub(pattern, lambda match: match.group(1), i) if isinstance(i, str) else i for i in stmts]
        stmts += ['stop']
        new_stmts = []
        for i in stmts:
            if isinstance(i, Return):
                raise CompileError('Can not return at here')
            elif isinstance(i, Break):
                raise CompileError('Can not break at here')
            elif isinstance(i, Continue):
                raise CompileError('Can not continue at here')
            elif isinstance(i, Global):
                raise CompileError('Global can only in function')
            elif isinstance(i, Label):
                new_stmts.append(f'{i.label}:')
            elif isinstance(i, Goto):
                new_stmts.append(f'jump {i.label} always 0 0')
            else:
                new_stmts.append(i)
        return '\n'.join(new_stmts)
    
    def stmt(self, args):
        return args[0]

    def _call_userfunc_token(self, token: Token):
        env.pos = token.end_line, token.end_column
        return super()._call_userfunc_token(token)
    
    def simple_stmt(self, args):
        return args[0]
    
    def continue_(self, args):
        return [Continue()]
    
    def break_(self, args):
        return [Break()]
    
    def global_(self, args):
        vars = [i for i in args if i]
        return [Global(vars)]
    
    def return_(self, args):
        ret_val = [i for i in args if i]
        if not ret_val:
            ret_val = [Single('null')]
        return [Return(*ret_val)]
    
    def set(self, args):
        expr = args[1]
        if hasattr(expr, 'func'):
            if (1 != expr.func.val_count) and expr.func.check_return_count:
                raise CompileError(f'Function {expr.func.name} return {expr.func.val_count} value(s) but 1 variable(s) are at left, use "@nocheckreturn" to pass the compilation')
        return MlogStmt.from_name('set').generate(*args)
    
    def unpack_return(self, args):
        *vars, expr = args
        vars = [i for i in vars if i]
        ret = []
        if (len(vars) != expr.func.val_count) and expr.func.check_return_count:
            raise CompileError(f'Function {expr.func.name} return {expr.func.val_count} value(s) but {len(vars)} variable(s) are at left, use "@nocheckreturn" to pass the compilation')
        expr_code = expr.expr_code(f'__temp{env.counter()}')
        ret.extend(expr_code.previous_code)
        for i in range(len(vars)):
            ret.extend(MlogStmt.from_name('set').generate(vars[i], Single(f'__return{i}')))
        return ret
    
    def setmem(self, args):
        return MlogStmt.from_name('write').generate(args[2], args[0], args[1])
    
    def control_stmt(self, args):
        expr, attr, *vals = args
        if isinstance(expr, Single) and expr.single == '@unit':
            try:
                return self.func_stmt([f'__buildin_Ucontrol_method_{attr}', *vals])
            except CompileError as e:
                if e.args[0].startswith('Undefined function'):
                    return self.func_stmt([f'__buildin_Ulocate_method_{attr}', *vals])
                raise e
        vals = [i for i in vals if i]
        new_vals = [Single('0') for _ in range(4)]
        for i in range(len(vals)):
            new_vals[i] = vals[i]
        return MlogStmt.from_name('control').generate(Single(attr), expr, *new_vals)

    def decorator(self, args):
        return [i for i in args if i is not None]
    
    def func_decl(self, args):
        decorator, name, *param, block = args
        # 展平 block，确保 Return/Break/Continue 等哨兵对象能被正确检测
        block = self._flatten(block)
        for i in block:
            if isinstance(i, Break):
                raise CompileError('Can not break at here')
            elif isinstance(i, Continue):
                raise CompileError('Can not continue at here')
        param = [i for i in param if i]
        if 'override' in decorator:
            if name not in env.funcs:
                raise CompileError(f'Function {name} does not exist, can not override')
            del env.funcs[name]
        func = Func(name, param, block)
        for i in decorator:
            match i:
                case 'nocheckreturn':
                    func.check_return_count = False
                case 'override':
                    pass
                case unknown:
                    raise CompileError(f'Unknown decorator {unknown}')
        env.current_func = None
        env.current_global.clear()
        return []
    
    def create_obj(self, args):
        name, type, *ar = args
        ar = [i for i in ar if i]
        if env.current_func and name not in env.current_global:
            name = f'__func_{env.current_func}_{name}'
        return CreateObj(name, type, *ar).generate()
    
    def copy_obj(self, args):
        new, origin = args
        if env.current_func and new not in env.current_global:
            new = f'__func_{env.current_func}_{new}'
        if env.current_func and origin not in env.current_global:
            origin = f'__func_{env.current_func}_{origin}'
        return CopyObj(new, origin).generate()
    
    def CLASS(self, args):
        ret = str(args)
        env.current_class.append(ret)
        return ret
    
    def CLASS_BEGIN(self, args):
        Class(*env.current_class)
        return None
    
    def class_decl(self, args):
        env.current_class.clear()
        return []

    def METH(self, args):
        ret = str(args)
        env.current_func = f'{env.current_class[0]}_method_{ret}'
        return ret
    
    def method(self, args):
        decorator, name, *param, block = args
        # 展平 block，确保 Return/Break/Continue 等哨兵对象能被正确检测
        block = self._flatten(block)
        for i in block:
            if isinstance(i, Break):
                raise CompileError('Can not break at here')
            elif isinstance(i, Continue):
                raise CompileError('Can not continue at here')
        param = [i for i in param if i]
        try:
            super = env.current_class[1]
        except:
            super = None
        if 'override' in decorator:
            if not super:
                raise CompileError(f'{env.current_class[0]} has no super class, can not override {env.current_class[0]}.{name}')
            if f'{super}_method_{name}' not in env.funcs:
                raise CompileError(f'{super}.{name} does not exist, can not override')
        else:
            if f'{super}_method_{name}' in env.funcs:
                raise CompileError(f'Use "@override" to override {super}.{name}')
        func = Func(f'{env.current_class[0]}_method_{name}', param, block)
        for i in decorator:
            match i:
                case 'nocheckreturn':
                    func.check_return_count = False
                case 'override':
                    pass
                case unknown:
                    raise CompileError(f'Unknown decorator {unknown}')
        env.current_func = None
        env.current_global.clear()
        return []
    
    def func_stmt(self, args):
        name, *param = args
        param = [i for i in param if i]
        if '.' in name:
            obj, meth = name.split('.')
            if obj == 'this' and env.current_class:
                return [DeferredMethodCall(meth, param, env.current_class[0])]
            if env.current_func and obj not in env.current_global:
                obj = f'__func_{env.current_func}_{obj}'
            return env.class_of(obj).get_method(meth, obj).generate(*param)
        if any(isinstance(p, DeferredFuncExpr) for p in param):
            return [DeferredStmt(name, param)]
        # 在类方法内部用全名 X_method_Y 调用方法时（如super调用），设置 this 为 $this$
        if env.current_class and '_method_' in name and name in env.funcs:
            func = env.get_func(name)
            func.this = '$this$'
            return func.generate(*param)
        return env.get_func(name).generate(*param)
    
    def block(self, args):
        return self._flatten(args)

    def MLOG(self, args):
        return str(args)
    
    def mlog(self, args):
        text = [i.strip() for i in (args[0] or '').splitlines() if i.strip()]
        return ['# begin mlog'] + text + ['# end mlog']
    
    def radar0(self, args):
        var, *fliter, sort = args
        lst = [Single('any') for _ in range(3)]
        if len(fliter) > 3:
            raise CompileError('Fliter amount can not more than 3')
        for i in range(len(fliter)):
            lst[i] = Single(fliter[i])
        def expr_code(self, var_name):
            return ExprCode(
                MlogStmt.from_name('radar').generate(
                    *lst, Single(sort), var, Single('0'), Single(var_name)
                ),
                var_name
            ) if var.single != '@unit' else ExprCode(
                MlogStmt.from_name('uradar').generate(
                    *lst, Single(sort), 0, Single('0'), Single(var_name)
                ),
                var_name
            )
        return type('Radar', (Expr,), {'expr_code': expr_code})()
    
    def radar1(self, args):
        var, *fliter, sort = args
        lst = [Single('any') for _ in range(3)]
        if len(fliter) > 3:
            raise CompileError('Fliter amount can not more than 3')
        for i in range(len(fliter)):
            lst[i] = Single(fliter[i])
        def expr_code(self, var_name):
            return ExprCode(
                MlogStmt.from_name('radar').generate(
                    *lst, Single(sort), var, Single('1'), Single(var_name)
                ),
                var_name
            ) if var.single != '@unit' else ExprCode(
                MlogStmt.from_name('uradar').generate(
                    *lst, Single(sort), Single('0'), Single('1'), Single(var_name)
                ),
                var_name
            )
        return type('Radar', (Expr,), {'expr_code': expr_code})()
    
    def if_(self, args):
        args = [i for i in args if i is not None]
        lst = [tuple[Expr, list[str]](args[i: i + 2]) for i in range(0, len(args), 2)]
        if len(lst[-1]) == 1:
            ifs = lst[:-1]
            else_ = lst[-1][0]
        else:
            ifs = lst
            else_ = []
        ret = []
        end_label = f'__label_if_end{env.counter()}'
        self_label = None
        next_label = f'__label_if_next{env.counter()}'
        for i in ifs:
            generated = MlogStmt.from_name('jump unless').generate(Single(next_label), i[0])
            label = [f'{self_label}:'] if self_label else []
            ret.extend(label + generated + i[1] + [f'jump {end_label} always 0 0'])
            self_label = next_label
            next_label = f'__label_if_next{env.counter()}'
        ret.append(f'{self_label}:')
        ret.extend(else_)
        ret.append(f'{end_label}:')
        return ['# begin if'] + ret + ['# end if']
    
    def for_(self, args):
        init, condition, update, block = args
        begin_label = f'__lebel_for_{env.counter()}'
        end_label = f'__lebel_for_{env.counter()}'
        ret = []
        if init:
            ret.extend(self._flatten([init]))
        ret += [f'{begin_label}:']
        if condition:
            code: ExprCode = condition.expr_code(f'__for_condition{env.counter()}')
            ret += code.previous_code
            ret += MlogStmt.from_name('jump unless').generate(Single(end_label), Single(code.reference))
        new_block = []
        for i in block:
            if isinstance(i, Return):
                raise CompileError('Can not return at here')
            elif isinstance(i, Break):
                new_block.append(f'jump {end_label} always 0 0')
            elif isinstance(i, Continue):
                if update:
                    new_block.extend(self._flatten([update]))
                new_block.append(f'jump {begin_label} always 0 0')
            else:
                new_block.append(i)
        ret += new_block
        if update:
            ret.extend(self._flatten([update]))
        ret += [f'jump {begin_label} always 0 0']
        ret += [f'{end_label}:']
        return ['# begin for'] + ret + ['# end for']
    
    def ESCAPED_STRING1(self, args):
        return json.dumps(literal_eval(str(args)), ensure_ascii=False)
    
    def ESCAPED_STRING2(self, args):
        return str(args)

    def label(self, args):
        return [Label(args[0])]
    
    def goto(self, args):
        return [Goto(args[0])]
    
    def printf(self, args):
        exprs, target = args
        ret = []
        for i in exprs or []:
            i: Expr
            if getattr(i, '_is_char', False):
                expr_code = i.expr_code(f'__temp{env.counter()}')
                ret.extend(expr_code.previous_code)
                ret.append(f'printchar {expr_code.reference}')
            else:
                expr_code = i.expr_code(f'__temp{env.counter()}')
                ret.extend(expr_code.previous_code)
                ret.append(f'print {expr_code.reference}')
        if target:
            target: Expr
            expr_code = target.expr_code(f'__temp{env.counter()}')
            ret.extend(expr_code.previous_code)
            ret.append(f'printflush {expr_code.reference}')
        return self._flatten(ret)
    
    def tmpl_str(self, args):
        return [i for i in args if i]
    
    def tmpl_char(self, args):
        ret = args[0]
        ret._is_char = True
        return ret

    def TMPL_WS(self, args):
        return Single(json.dumps(str(args), ensure_ascii=False))
    
    def tmpl_str_expr(self, args):
        return args[0]
    
    def TMPL_CONTENT(self, args):
        string = str(args)
        string = string.replace(r'\$', '$').replace(r'\`', '`').replace(r'\n', '\n')
        return Single(json.dumps(string, ensure_ascii=False))
    
    def str(self, args):
        return Single(args[0])
    
    def VAR(self, args):
        string = str(args)
        if string.startswith('@') or (string in ['true', 'false', 'null']):
            if '.' in string:
                raise CompileError(f'Invailable variable name {string}')
            return Single(string)
        if '.' in string:
            a, b = string.split('.', maxsplit=1)
            if a == 'this' and env.current_func and env.current_class:
                a = '$this$'
                env.classes[env.current_class[0]].attr.append(b)
            else:
                if a not in env.objs:
                    raise CompileError(f'Variable {a} is not object, can not access attribute')
                if b not in env.classes[env.objs[a]].get_attrs():
                    raise CompileError(f'{env.objs[a]} object has no attribute {b}')
            string = a + '_markforattr_' + b
            return Single(f'%{string}%')
        else:
            return Single(f'%{string}%')

    def NAME(self, args):
        return str(args)
    
    def NUMBER(self, args):
        return Single(str(args))
    
    def atom(self, args):
        return args[0]
    
    def expr(self, args):
        return args[0]
    
    def sensor(self, args):
        def expr_code(self, var_name):
            return ExprCode(
                MlogStmt.from_name('sensor').generate(Single(var_name), args[0], Single(f'@{args[1]}')),
                var_name
            )
        return type('Getattr', (Expr,), {'expr_code': expr_code})()

    def getmem(self, args):
        def expr_code(self, var_name):
            return ExprCode(
                MlogStmt.from_name('read').generate(Single(var_name), args[0], args[1]),
                var_name
            )
        return type('Getmem', (Expr,), {'expr_code': expr_code})()
    
    def three_unit(self, args):
        def expr_code(self, var_name):
            return ExprCode(
                MlogStmt.from_name('select').generate(Single(var_name), args[1], args[0], args[2]),
                var_name
            )
        return type('ThreeUnit', (Expr,), {'expr_code': expr_code})()
    
    def op(self, args):
        if len(args) == 1:
            return args[0]
        for target_op in LEVEL:
            while True:
                match merge_op(args, target_op):
                    case None:
                        break
                    case new:
                        args = new
        assert len(args) == 1
        return args[0]
    
    def OPERATOR(self, args):
        return str(args)

    def func_return(self, args):
        name, *param = args
        param = [i for i in param if i]
        if '.' in name:
            obj, meth = name.split('.')
            if obj == 'this' and env.current_class:
                return DeferredFuncExpr(meth, param, env.current_class[0])
            if env.current_func and obj not in env.current_global:
                obj = f'__func_{env.current_func}_{obj}'
            func = env.class_of(obj).get_method(meth, obj)
        else:
            func = env.get_func(name)
        if env.current_class and '_method_' in name and name in env.funcs:
            func.this = '$this$'
        multi = False
        for i in func.block:
            if isinstance(i, Return) and len(i.ret_val) > 1:
                multi = True
                break
        if func.is_expr and multi:
            print(f'[warning] Function {func.name} is used as expression. Taking first return value as the expression value', file=sys.stderr)
        return func.to_expr(*param)
    
    def control_return(self, args):
        name, *expr = args
        try:
            return self.func_return([f'__buildin_Ucontrol_method_{name}', *expr])
        except CompileError as e:
            if e.args[0].startswith('Undefined function'):
                return self.func_return([f'__buildin_Ulocate_method_{name}', *expr])
            raise e
    
    def control_for_unpack(self, args):
        name, *expr = args
        try:
            return self.func_return_for_unpack([f'__buildin_Ucontrol_method_{name}', *expr])
        except CompileError as e:
            if e.args[0].startswith('Undefined function'):
                return self.func_return_for_unpack([f'__buildin_Ulocate_method_{name}', *expr])
            raise e

    def bind(self, args):
        name, = args
        param = '@' + name if not name.startswith('@') else name
        return self.func_stmt(['__buildin_ubind', Single(param)])
    
    def func_return_for_unpack(self, args):
        name, *param = args
        param = [i for i in param if i]
        if '.' in name:
            obj, meth = name.split('.')
            if obj == 'this' and env.current_class:
                ret = env.classes[env.current_class[0]].get_method(meth, '$this$').to_expr(*param)
                return ret
            if env.current_func and obj not in env.current_global:
                obj = f'__func_{env.current_func}_{obj}'
            return env.class_of(obj).get_method(meth, obj).to_expr(*param)
        func = env.get_func(name)
        if env.current_class and '_method_' in name and name in env.funcs:
            func.this = '$this$'
        return func.to_expr(*param)
    
    def FUNC(self, args):
        ret = str(args)
        env.current_func = ret
        return ret

trans = Trans()

def compile(code: str, source = None, include: list[str | Path] = None, copy = True) -> str:
    env.__init__()
    preprocesser = MyPreprocessor()
    preprocesser.add_path(str(files('mlogscript') / '_include'))
    for i in include or []:
        preprocesser.add_path(str(i))
    preprocesser.parse('#include <buildin.mls>\n' + code, source)
    string = io.StringIO()
    preprocesser.write(string)
    preprocessed = string.getvalue()
    lines = preprocessed.splitlines(keepends=True)
    new_code = ''
    line_mark = []
    for i in range(len(lines)):
        line = lines[i]
        if line.startswith('#line'):
            new_code += '\n'
            splited = line.split()
            line_mark.append((i + 1, splited[2], int(splited[1])))
        else:
            new_code += line
    Operator.refresh()
    ops = ' | '.join(f'"{i.op}"' for i in Operator.instances)
    lark = Lark(grammer.replace('//operators', ops), parser='earley', lexer='dynamic_complete')
    def add_note(e: Exception, line: int, col: int):
        if not source:
            raise e from None
        for i in range(len(line_mark)):
            if line_mark[i][0] > line:
                target = line_mark[i - 1]
                break
        else:
            target = line_mark[-1]
        line = line - target[0] + target[2] - 1
        file = target[1]
        e.add_note(f'{file} line {line} column {col}')
    try:
        ret = trans.transform(lark.parse(new_code))
        if copy: pyperclip.copy(ret)
        return ret
    except VisitError as e:
        if isinstance(e.orig_exc, CompileError):
            if env.pos:
                add_note(e.orig_exc, env.pos[0], env.pos[1])
            raise e.orig_exc from None
        else:
            raise e
    except UnexpectedInput as e:
        add_note(e, e.line, e.column)
        raise e from None
    except CompileError as e:
        if env.pos:
            add_note(e.orig_exc, env.pos[0], env.pos[1])
        raise e

def compile_file(file: str | Path, include: list[str | Path] = None, copy = True):
    return compile(Path(file).read_text('utf-8'), file, include, copy)
