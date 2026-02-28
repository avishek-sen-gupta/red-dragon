program M;

function hammingDistance(s1: string; s2: string; n: integer): integer;
var
    distance: integer;
    i: integer;
begin
    distance := 0;
    i := 0;
    while i < n do
    begin
        if s1[i] <> s2[i] then
        begin
            distance := distance + 1;
        end;
        i := i + 1;
    end;
    hammingDistance := distance;
end;

var answer: integer;
begin
    answer := hammingDistance('GAGCCTACTAACGGGAT', 'CATCGTAATGACGGCCT', 17);
end.
