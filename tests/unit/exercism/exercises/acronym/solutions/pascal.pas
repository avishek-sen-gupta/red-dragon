program M;

function toUpperChar(c: string): string;
begin
    if c = 'a' then begin toUpperChar := 'A'; exit; end;
    if c = 'b' then begin toUpperChar := 'B'; exit; end;
    if c = 'c' then begin toUpperChar := 'C'; exit; end;
    if c = 'd' then begin toUpperChar := 'D'; exit; end;
    if c = 'e' then begin toUpperChar := 'E'; exit; end;
    if c = 'f' then begin toUpperChar := 'F'; exit; end;
    if c = 'g' then begin toUpperChar := 'G'; exit; end;
    if c = 'h' then begin toUpperChar := 'H'; exit; end;
    if c = 'i' then begin toUpperChar := 'I'; exit; end;
    if c = 'j' then begin toUpperChar := 'J'; exit; end;
    if c = 'k' then begin toUpperChar := 'K'; exit; end;
    if c = 'l' then begin toUpperChar := 'L'; exit; end;
    if c = 'm' then begin toUpperChar := 'M'; exit; end;
    if c = 'n' then begin toUpperChar := 'N'; exit; end;
    if c = 'o' then begin toUpperChar := 'O'; exit; end;
    if c = 'p' then begin toUpperChar := 'P'; exit; end;
    if c = 'q' then begin toUpperChar := 'Q'; exit; end;
    if c = 'r' then begin toUpperChar := 'R'; exit; end;
    if c = 's' then begin toUpperChar := 'S'; exit; end;
    if c = 't' then begin toUpperChar := 'T'; exit; end;
    if c = 'u' then begin toUpperChar := 'U'; exit; end;
    if c = 'v' then begin toUpperChar := 'V'; exit; end;
    if c = 'w' then begin toUpperChar := 'W'; exit; end;
    if c = 'x' then begin toUpperChar := 'X'; exit; end;
    if c = 'y' then begin toUpperChar := 'Y'; exit; end;
    if c = 'z' then begin toUpperChar := 'Z'; exit; end;
    toUpperChar := c;
end;

function abbreviate(phrase: string; n: integer): string;
var
    result: string;
    atWordStart: integer;
    i: integer;
    c: string;
begin
    result := '';
    atWordStart := 1;
    i := 0;
    while i < n do
    begin
        c := phrase[i];
        if c = ' ' then
        begin
            atWordStart := 1;
            i := i + 1;
        end
        else if c = '-' then
        begin
            atWordStart := 1;
            i := i + 1;
        end
        else if c = '_' then
        begin
            atWordStart := 1;
            i := i + 1;
        end
        else
        begin
            if atWordStart = 1 then
            begin
                result := result + toUpperChar(c);
                atWordStart := 0;
            end;
            i := i + 1;
        end;
    end;
    abbreviate := result;
end;

var answer: string;
begin
    answer := abbreviate('Portable Network Graphics', 25);
end.
