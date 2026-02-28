program M;

function toLowerChar(c: string): string;
begin
    if c = 'A' then begin toLowerChar := 'a'; exit; end;
    if c = 'B' then begin toLowerChar := 'b'; exit; end;
    if c = 'C' then begin toLowerChar := 'c'; exit; end;
    if c = 'D' then begin toLowerChar := 'd'; exit; end;
    if c = 'E' then begin toLowerChar := 'e'; exit; end;
    if c = 'F' then begin toLowerChar := 'f'; exit; end;
    if c = 'G' then begin toLowerChar := 'g'; exit; end;
    if c = 'H' then begin toLowerChar := 'h'; exit; end;
    if c = 'I' then begin toLowerChar := 'i'; exit; end;
    if c = 'J' then begin toLowerChar := 'j'; exit; end;
    if c = 'K' then begin toLowerChar := 'k'; exit; end;
    if c = 'L' then begin toLowerChar := 'l'; exit; end;
    if c = 'M' then begin toLowerChar := 'm'; exit; end;
    if c = 'N' then begin toLowerChar := 'n'; exit; end;
    if c = 'O' then begin toLowerChar := 'o'; exit; end;
    if c = 'P' then begin toLowerChar := 'p'; exit; end;
    if c = 'Q' then begin toLowerChar := 'q'; exit; end;
    if c = 'R' then begin toLowerChar := 'r'; exit; end;
    if c = 'S' then begin toLowerChar := 's'; exit; end;
    if c = 'T' then begin toLowerChar := 't'; exit; end;
    if c = 'U' then begin toLowerChar := 'u'; exit; end;
    if c = 'V' then begin toLowerChar := 'v'; exit; end;
    if c = 'W' then begin toLowerChar := 'w'; exit; end;
    if c = 'X' then begin toLowerChar := 'x'; exit; end;
    if c = 'Y' then begin toLowerChar := 'y'; exit; end;
    if c = 'Z' then begin toLowerChar := 'z'; exit; end;
    toLowerChar := c;
end;

function isIsogram(word: string; n: integer): integer;
var
    i: integer;
    j: integer;
begin
    i := 0;
    while i < n do
    begin
        if word[i] = ' ' then
        begin
            i := i + 1;
            continue;
        end;
        if word[i] = '-' then
        begin
            i := i + 1;
            continue;
        end;
        j := i + 1;
        while j < n do
        begin
            if word[j] = ' ' then
            begin
                j := j + 1;
                continue;
            end;
            if word[j] = '-' then
            begin
                j := j + 1;
                continue;
            end;
            if toLowerChar(word[i]) = toLowerChar(word[j]) then
            begin
                isIsogram := 0;
                exit;
            end;
            j := j + 1;
        end;
        i := i + 1;
    end;
    isIsogram := 1;
end;

var answer: integer;
begin
    answer := isIsogram('isogram', 7);
end.
