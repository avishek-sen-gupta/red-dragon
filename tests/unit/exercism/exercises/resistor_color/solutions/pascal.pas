program M;

function colorCode(color: string): integer;
begin
    if color = 'black' then
    begin
        colorCode := 0;
        exit;
    end;
    if color = 'brown' then
    begin
        colorCode := 1;
        exit;
    end;
    if color = 'red' then
    begin
        colorCode := 2;
        exit;
    end;
    if color = 'orange' then
    begin
        colorCode := 3;
        exit;
    end;
    if color = 'yellow' then
    begin
        colorCode := 4;
        exit;
    end;
    if color = 'green' then
    begin
        colorCode := 5;
        exit;
    end;
    if color = 'blue' then
    begin
        colorCode := 6;
        exit;
    end;
    if color = 'violet' then
    begin
        colorCode := 7;
        exit;
    end;
    if color = 'grey' then
    begin
        colorCode := 8;
        exit;
    end;
    if color = 'white' then
    begin
        colorCode := 9;
        exit;
    end;
    colorCode := -1;
end;

var answer: integer;
begin
    answer := colorCode('black');
end.
