program M;

function toRna(dna: string; n: integer): string;
var
    result: string;
    i: integer;
begin
    result := '';
    i := 0;
    while i < n do
    begin
        if dna[i] = 'G' then
        begin
            result := result + 'C';
        end;
        if dna[i] = 'C' then
        begin
            result := result + 'G';
        end;
        if dna[i] = 'T' then
        begin
            result := result + 'A';
        end;
        if dna[i] = 'A' then
        begin
            result := result + 'U';
        end;
        i := i + 1;
    end;
    toRna := result;
end;

var answer: string;
begin
    answer := toRna('ACGTGGTCTTAA', 12);
end.
