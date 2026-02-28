program M;

function nthPrime(n: integer): integer;
var
    count: integer;
    candidate: integer;
    isPrime: integer;
    divisor: integer;
begin
    count := 0;
    candidate := 2;
    while count < n do
    begin
        isPrime := 1;
        divisor := 2;
        while divisor * divisor <= candidate do
        begin
            if candidate mod divisor = 0 then
            begin
                isPrime := 0;
            end;
            divisor := divisor + 1;
        end;
        if isPrime = 1 then
        begin
            count := count + 1;
        end;
        if count < n then
        begin
            candidate := candidate + 1;
        end;
    end;
    nthPrime := candidate;
end;

var answer: integer;
begin
    answer := nthPrime(1);
end.
