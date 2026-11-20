import re
from typing import Callable
from pcpp import Preprocessor
from pcpp.ply.ply.lex import LexToken
from pcpp.parser import Macro
from ._parse import CompileError, Operator


MARK = '$-$mark$-$'
pattern = re.compile(r'[a-zA-Z0-9_]')
class MyPreprocessor(Preprocessor):
    def __init__(self, lexer=None):
        super().__init__(lexer)
        self._custom_macros: dict[str, Callable[[str], str]] = {}
        self._new_macro('CAPITALIZE', f'name', ['name'], False, lambda name: name.capitalize())
        self._new_macro('PASTE', f'__VA_ARGS__', ['__VA_ARGS__'], True, lambda text: ''.join(i.strip() for i in text.split(',')))
    
    def _new_macro(self, name: str, body: str, arglist = None, variadic = False, callback: Callable[[str], str] = None):
        if callback:
            self._custom_macros[name] = callback
        m = Macro(name, self._get_tokens((f'{MARK} ' if callback is not None else '') + body), arglist=arglist, variadic=variadic)
        self.macro_prescan(m)
        self.macros[name] = m
    
    def _get_tokens(self, string: str):
        self.lexer.input(string)
        result = []
        while True:
            tok = self.lexer.token()
            if not tok:
                break
            result.append(tok)
        return result

    def expand_macros(self, tokens, expanding_from=[]):
        if expanding_from:
            name = expanding_from[-1]
            string = ''.join(i.value for i in tokens)
            if name and name in self._custom_macros and string.startswith(MARK):
                try:
                    return self._get_tokens(self._custom_macros[name](string[len(MARK):].strip()))
                except Exception as e:
                    raise CompileError(f'Error on macro {repr(name)} expanding') from e
        return super().expand_macros(tokens, expanding_from)

    def on_comment(self, tok):
        if tok.type == 'CPP_COMMENT2' and not tok.value.startswith('//*'):
            return tok.value
        return super().on_comment(tok)

    def on_directive_unknown(self, directive: LexToken, toks: list[LexToken], ifpassthru, precedingtoks):
        match directive.value:
            case 'pragma':
                args: list[str] = ''.join(i.value for i in toks).split()
                error = CompileError(f'Pragma arguments error {args}')
                match args:
                    case 'operator', op, ref, level:
                        if re.match(pattern, op):
                            raise CompileError(f'Can not define operator {op}')
                        try:
                            level = int(level)
                        except:
                            raise error
                        for i in Operator.instances:
                            if i.op == op:
                                i.ref = ref
                                i.lev = level
                                break
                        else:
                            Operator.instances.append(Operator(op, ref, level))
                    case _:
                        raise error
                return ''
            case 'error' | 'warning':
                return super().on_directive_unknown(directive, toks, ifpassthru, precedingtoks)
            case _:
                raise CompileError(f'Unknown preprocessor command {directive.value}')
