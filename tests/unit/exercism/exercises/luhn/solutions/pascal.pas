program M;

function charToDigit(c: string): integer;
begin
    if c = '0' then begin charToDigit := 0; exit; end;
    if c = '1' then begin charToDigit := 1; exit; end;
    if c = '2' then begin charToDigit := 2; exit; end;
    if c = '3' then begin charToDigit := 3; exit; end;
    if c = '4' then begin charToDigit := 4; exit; end;
    if c = '5' then begin charToDigit := 5; exit; end;
    if c = '6' then begin charToDigit := 6; exit; end;
    if c = '7' then begin charToDigit := 7; exit; end;
    if c = '8' then begin charToDigit := 8; exit; end;
    if c = '9' then begin charToDigit := 9; exit; end;
    charToDigit := -1;
end;

function isValid(number: string; n: integer): integer;
var
    digitCount: integer;
    i: integer;
    c: string;
    d: integer;
    total: integer;
    count: integer;
begin
    digitCount := 0;
    i := 0;
    while i < n do
    begin
        c := number[i];
        if c = ' ' then
        begin
            i := i + 1;
        end
        else
        begin
            d := charToDigit(c);
            if d = -1 then
            begin
                isValid := 0;
                exit;
            end;
            digitCount := digitCount + 1;
            i := i + 1;
        end;
    end;
    if digitCount <= 1 then
    begin
        isValid := 0;
        exit;
    end;
    total := 0;
    count := 0;
    i := n - 1;
    while i >= 0 do
    begin
        c := number[i];
        if c = ' ' then
        begin
            i := i - 1;
        end
        else
        begin
            d := charToDigit(c);
            if count mod 2 = 1 then
            begin
                d := d * 2;
                if d > 9 then
                begin
                    d := d - 9;
                end;
            end;
            total := total + d;
            count := count + 1;
            i := i - 1;
        end;
    end;
    if total mod 10 = 0 then
    begin
        isValid := 1;
        exit;
    end;
    isValid := 0;
end;

var answer: integer;
begin
    answer := isValid('059', 3);
end.
