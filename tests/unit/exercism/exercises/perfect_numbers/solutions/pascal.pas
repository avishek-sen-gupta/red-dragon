program M;

function classify(n: integer): string;
var
    total: integer;
    i: integer;
begin
    total := 0;
    i := 1;
    while i < n do
    begin
        if n mod i = 0 then
        begin
            total := total + i;
        end;
        i := i + 1;
    end;
    if total = n then
    begin
        classify := 'perfect';
        exit;
    end;
    if total > n then
    begin
        classify := 'abundant';
        exit;
    end;
    classify := 'deficient';
end;

var answer: string;
begin
    answer := classify(6);
end.
