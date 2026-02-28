program M;

function square(n: integer): integer;
var
    result: integer;
    i: integer;
begin
    result := 1;
    i := 1;
    while i < n do
    begin
        result := result * 2;
        i := i + 1;
    end;
    square := result;
end;

function total(): integer;
var
    result: integer;
    power: integer;
    i: integer;
begin
    result := 0;
    power := 1;
    i := 1;
    while i <= 64 do
    begin
        result := result + power;
        power := power * 2;
        i := i + 1;
    end;
    total := result;
end;

var answer: integer;
begin
    answer := square(1);
end.
