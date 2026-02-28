program M;

function squareOfSum(n: integer): integer;
var
    total: integer;
    i: integer;
begin
    total := 0;
    i := 1;
    while i <= n do
    begin
        total := total + i;
        i := i + 1;
    end;
    squareOfSum := total * total;
end;

function sumOfSquares(n: integer): integer;
var
    total: integer;
    i: integer;
begin
    total := 0;
    i := 1;
    while i <= n do
    begin
        total := total + i * i;
        i := i + 1;
    end;
    sumOfSquares := total;
end;

function differenceOfSquares(n: integer): integer;
begin
    differenceOfSquares := squareOfSum(n) - sumOfSquares(n);
end;

var answer: integer;
begin
    answer := differenceOfSquares(10);
end.
