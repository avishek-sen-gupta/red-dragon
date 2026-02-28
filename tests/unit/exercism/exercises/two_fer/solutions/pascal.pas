program M;

function twoFer(name: string): string;
begin
    twoFer := 'One for ' + name + ', one for me.';
end;

var answer: string;
begin
    answer := twoFer('Alice');
end.
