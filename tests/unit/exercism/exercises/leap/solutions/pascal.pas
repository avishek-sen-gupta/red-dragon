program M;

function leapYear(year: integer): integer;
begin
    if year mod 400 = 0 then
    begin
        leapYear := 1;
        exit;
    end;
    if year mod 100 = 0 then
    begin
        leapYear := 0;
        exit;
    end;
    if year mod 4 = 0 then
    begin
        leapYear := 1;
        exit;
    end;
    leapYear := 0;
end;

var answer: integer;
begin
    answer := leapYear(2000);
end.
