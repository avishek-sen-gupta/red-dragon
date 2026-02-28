program M;

function isUpperChar(c: string): integer;
begin
    if c = 'A' then begin isUpperChar := 1; exit; end;
    if c = 'B' then begin isUpperChar := 1; exit; end;
    if c = 'C' then begin isUpperChar := 1; exit; end;
    if c = 'D' then begin isUpperChar := 1; exit; end;
    if c = 'E' then begin isUpperChar := 1; exit; end;
    if c = 'F' then begin isUpperChar := 1; exit; end;
    if c = 'G' then begin isUpperChar := 1; exit; end;
    if c = 'H' then begin isUpperChar := 1; exit; end;
    if c = 'I' then begin isUpperChar := 1; exit; end;
    if c = 'J' then begin isUpperChar := 1; exit; end;
    if c = 'K' then begin isUpperChar := 1; exit; end;
    if c = 'L' then begin isUpperChar := 1; exit; end;
    if c = 'M' then begin isUpperChar := 1; exit; end;
    if c = 'N' then begin isUpperChar := 1; exit; end;
    if c = 'O' then begin isUpperChar := 1; exit; end;
    if c = 'P' then begin isUpperChar := 1; exit; end;
    if c = 'Q' then begin isUpperChar := 1; exit; end;
    if c = 'R' then begin isUpperChar := 1; exit; end;
    if c = 'S' then begin isUpperChar := 1; exit; end;
    if c = 'T' then begin isUpperChar := 1; exit; end;
    if c = 'U' then begin isUpperChar := 1; exit; end;
    if c = 'V' then begin isUpperChar := 1; exit; end;
    if c = 'W' then begin isUpperChar := 1; exit; end;
    if c = 'X' then begin isUpperChar := 1; exit; end;
    if c = 'Y' then begin isUpperChar := 1; exit; end;
    if c = 'Z' then begin isUpperChar := 1; exit; end;
    isUpperChar := 0;
end;

function isLowerChar(c: string): integer;
begin
    if c = 'a' then begin isLowerChar := 1; exit; end;
    if c = 'b' then begin isLowerChar := 1; exit; end;
    if c = 'c' then begin isLowerChar := 1; exit; end;
    if c = 'd' then begin isLowerChar := 1; exit; end;
    if c = 'e' then begin isLowerChar := 1; exit; end;
    if c = 'f' then begin isLowerChar := 1; exit; end;
    if c = 'g' then begin isLowerChar := 1; exit; end;
    if c = 'h' then begin isLowerChar := 1; exit; end;
    if c = 'i' then begin isLowerChar := 1; exit; end;
    if c = 'j' then begin isLowerChar := 1; exit; end;
    if c = 'k' then begin isLowerChar := 1; exit; end;
    if c = 'l' then begin isLowerChar := 1; exit; end;
    if c = 'm' then begin isLowerChar := 1; exit; end;
    if c = 'n' then begin isLowerChar := 1; exit; end;
    if c = 'o' then begin isLowerChar := 1; exit; end;
    if c = 'p' then begin isLowerChar := 1; exit; end;
    if c = 'q' then begin isLowerChar := 1; exit; end;
    if c = 'r' then begin isLowerChar := 1; exit; end;
    if c = 's' then begin isLowerChar := 1; exit; end;
    if c = 't' then begin isLowerChar := 1; exit; end;
    if c = 'u' then begin isLowerChar := 1; exit; end;
    if c = 'v' then begin isLowerChar := 1; exit; end;
    if c = 'w' then begin isLowerChar := 1; exit; end;
    if c = 'x' then begin isLowerChar := 1; exit; end;
    if c = 'y' then begin isLowerChar := 1; exit; end;
    if c = 'z' then begin isLowerChar := 1; exit; end;
    isLowerChar := 0;
end;

function response(heyBob: string; n: integer): string;
var
    hasContent: integer;
    hasUpper: integer;
    hasLower: integer;
    lastNonSpace: string;
    i: integer;
    c: string;
    isYelling: integer;
    isQuestion: integer;
begin
    hasContent := 0;
    hasUpper := 0;
    hasLower := 0;
    lastNonSpace := '';
    i := 0;
    while i < n do
    begin
        c := heyBob[i];
        if c <> ' ' then
        begin
            hasContent := 1;
            lastNonSpace := c;
        end;
        if isUpperChar(c) = 1 then
        begin
            hasUpper := 1;
        end;
        if isLowerChar(c) = 1 then
        begin
            hasLower := 1;
        end;
        i := i + 1;
    end;
    if hasContent = 0 then
    begin
        response := 'Fine. Be that way!';
        exit;
    end;
    isYelling := 0;
    if hasUpper = 1 then
    begin
        if hasLower = 0 then
        begin
            isYelling := 1;
        end;
    end;
    isQuestion := 0;
    if lastNonSpace = '?' then
    begin
        isQuestion := 1;
    end;
    if isYelling = 1 then
    begin
        if isQuestion = 1 then
        begin
            response := 'Calm down!';
            exit;
        end;
        response := 'Whoa, chill out!';
        exit;
    end;
    if isQuestion = 1 then
    begin
        response := 'Sure.';
        exit;
    end;
    response := 'Whatever.';
end;

var answer: string;
begin
    answer := response('Tom-ay-to, tom-aaaah-to.', 24);
end.
