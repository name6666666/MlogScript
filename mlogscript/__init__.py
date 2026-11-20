"""
Mindustry C, A DSL supports you to edit mindustry logical processor as if writing advance language but not assembly.
Except solving issues on "this" grammer, super class calling and some bugs is by AI (aka the functions and classes which have doc string),
 all the implementations are by me.
```js
/*
comment1 (multi line)
*/
//* comment2 (single line)
//* assign statement
example = 1;
//* if statement
if 1 + 1 === 2 {
    ...
} elif [] == null {
    ...
} else {
    ...
}
//* for statement
for i = 0; i < 10; i = i + 1 {
    ...
}
//* function declaration
example(a, b) {
    return a, b; //* supporting multi return value
}
//* class declaration
class A extends B {
    constructor() {
        this.a = 1;
    }
    oncopy() { //* automatically calling oncopy when assignment
        ...
    }
    @override
    method() {
        this.a = 0;
    }
}
//* obj keyword
commonVar = 5;
obj objectVar = A();
```
```c
//* using C preprocessor as its preprocessor
#define MACRO 5
//* special preprocessor command, being used to create or modify operator
#pragma operator + add 2
#pragma operator ?> max 3
```
```js
//* getting content in memory block
memBlock = link(0); //* getlink
print(memBlock[0]);
printflush(link(1));
//* using ":" operator as sensor and control command
weapon = link(0);
weapon:shoot(enemy:x, enemy:y, true);
//* search keyword, elegent grammer for radar
target = block search enemy -health>;
target = block search ally <distance-;
x = (@unit search ally <health-):x;
"""

from ._register_stmt import *
from ._parse import compile, compile_file, CompileError
