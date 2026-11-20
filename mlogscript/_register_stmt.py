from ._stmt import MlogStmt


MlogStmt(['set', None, None])
MlogStmt(['getlink', None, None])
MlogStmt(['jump', None, 'notEqual', None, '0'], 'jump if')
MlogStmt(['jump', None, 'equal', None, '0'], 'jump unless')
MlogStmt(['write', None, None, None])
MlogStmt(['read', None, None, None])
MlogStmt(['select', None, 'notEqual', None, '0', None, None])
MlogStmt(['sensor', None, None, None])
MlogStmt(['control', None, None, None, None, None, None])
MlogStmt(['radar', None, None, None, None, None, None, None])
MlogStmt(['uradar', None, None, None, None, None, None, None])
