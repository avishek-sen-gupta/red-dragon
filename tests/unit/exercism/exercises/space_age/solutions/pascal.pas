program M;

function spaceAge(planet: string; seconds: integer): real;
var
    ratio: real;
begin
    ratio := 1.0;
    if planet = 'Mercury' then
    begin
        ratio := 0.2408467;
    end;
    if planet = 'Venus' then
    begin
        ratio := 0.61519726;
    end;
    if planet = 'Mars' then
    begin
        ratio := 1.8808158;
    end;
    if planet = 'Jupiter' then
    begin
        ratio := 11.862615;
    end;
    if planet = 'Saturn' then
    begin
        ratio := 29.447498;
    end;
    if planet = 'Uranus' then
    begin
        ratio := 84.016846;
    end;
    if planet = 'Neptune' then
    begin
        ratio := 164.79132;
    end;
    spaceAge := seconds / (31557600.0 * ratio);
end;

var answer: real;
begin
    answer := spaceAge('Earth', 1000000000);
end.
