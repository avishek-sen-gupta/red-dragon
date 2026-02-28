program M;

function reverseString(s: string; n: integer): string;
var
    result: string;
    i: integer;
begin
    result := '';
    i := n - 1;
    while i >= 0 do
    begin
        result := result + s[i];
        i := i - 1;
    end;
    reverseString := result;
end;

var answer: string;
begin
    answer := reverseString('robot', 5);
end.
