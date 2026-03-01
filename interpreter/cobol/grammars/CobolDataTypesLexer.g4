/*
* Copyright (C) 2024, Avishek Sen Gupta <avishek.sen.gupta@gmail.com>
* All rights reserved.
*
* This software may be modified and distributed under the terms
* of the MIT license. See the LICENSE file for details.
*/

lexer grammar CobolDataTypesLexer;

channels{COMMENTS, TECHNICAL}

// keywords

CURRENCY_SYMBOL : [\p{Sc}];

// whitespace, line breaks, comments, ...
NEWLINE : '\r'? '\n' -> channel(HIDDEN);
WS : [ \t\f]+ -> channel(HIDDEN);
COMMA : ',' -> channel(HIDDEN);

UNDERSCORECHAR : '_';
ZERO_WIDTH_SPACE: '\u200B';

fragment OCT_DIGIT        : [0-8] ;
fragment DIGIT: OCT_DIGIT | [9];

fragment LPARENCHAR : '(';
fragment RPARENCHAR : ')';

// case insensitive chars
fragment A:('a'|'A');
fragment B:('b'|'B');
fragment C:('c'|'C');
fragment D:('d'|'D');
fragment E:('e'|'E');
fragment F:('f'|'F');
fragment G:('g'|'G');
fragment H:('h'|'H');
fragment I:('i'|'I');
fragment J:('j'|'J');
fragment K:('k'|'K');
fragment L:('l'|'L');
fragment M:('m'|'M');
fragment N:('n'|'N');
fragment O:('o'|'O');
fragment P:('p'|'P');
fragment Q:('q'|'Q');
fragment R:('r'|'R');
fragment S:('s'|'S');
fragment T:('t'|'T');
fragment U:('u'|'U');
fragment V:('v'|'V');
fragment W:('w'|'W');
fragment X:('x'|'X');
fragment Y:('y'|'Y');
fragment Z:('z'|'Z');

CHAR_NINE : '9';
CHAR_Z : Z;
SIGN_SYMBOL : S;
DISPLAY_SIGN_SYMBOL : '-' -> channel(HIDDEN);
DECIMALPOINTLOCATOR : V;
VISUALDECIMALPOINT : '.' -> channel(HIDDEN);
SCALINGINDICATOR : P;
ALPHANUMERICINDICATOR : X;

fragment POSITIVEINTEGER: DIGIT+;
NUMBEROF : LPARENCHAR POSITIVEINTEGER RPARENCHAR;
POINTER : P O I N T E R;
