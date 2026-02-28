program M;

function collatzSteps(number: integer): integer;
var
    steps: integer;
begin
    steps := 0;
    while number <> 1 do
    begin
        if number mod 2 = 0 then
            number := number div 2
        else
            number := number * 3 + 1;
        steps := steps + 1;
    end;
    collatzSteps := steps;
end;

var answer: integer;
begin
    answer := collatzSteps(16);
end.
