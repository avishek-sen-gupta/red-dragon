program M;

function isEquilateral(a: integer; b: integer; c: integer): integer;
begin
    if a <= 0 then
    begin
        isEquilateral := 0;
        exit;
    end;
    if b <= 0 then
    begin
        isEquilateral := 0;
        exit;
    end;
    if c <= 0 then
    begin
        isEquilateral := 0;
        exit;
    end;
    if a + b <= c then
    begin
        isEquilateral := 0;
        exit;
    end;
    if b + c <= a then
    begin
        isEquilateral := 0;
        exit;
    end;
    if a + c <= b then
    begin
        isEquilateral := 0;
        exit;
    end;
    if a = b then
    begin
        if b = c then
        begin
            isEquilateral := 1;
            exit;
        end;
    end;
    isEquilateral := 0;
end;

function isIsosceles(a: integer; b: integer; c: integer): integer;
begin
    if a <= 0 then
    begin
        isIsosceles := 0;
        exit;
    end;
    if b <= 0 then
    begin
        isIsosceles := 0;
        exit;
    end;
    if c <= 0 then
    begin
        isIsosceles := 0;
        exit;
    end;
    if a + b <= c then
    begin
        isIsosceles := 0;
        exit;
    end;
    if b + c <= a then
    begin
        isIsosceles := 0;
        exit;
    end;
    if a + c <= b then
    begin
        isIsosceles := 0;
        exit;
    end;
    if a = b then
    begin
        isIsosceles := 1;
        exit;
    end;
    if b = c then
    begin
        isIsosceles := 1;
        exit;
    end;
    if a = c then
    begin
        isIsosceles := 1;
        exit;
    end;
    isIsosceles := 0;
end;

function isScalene(a: integer; b: integer; c: integer): integer;
begin
    if a <= 0 then
    begin
        isScalene := 0;
        exit;
    end;
    if b <= 0 then
    begin
        isScalene := 0;
        exit;
    end;
    if c <= 0 then
    begin
        isScalene := 0;
        exit;
    end;
    if a + b <= c then
    begin
        isScalene := 0;
        exit;
    end;
    if b + c <= a then
    begin
        isScalene := 0;
        exit;
    end;
    if a + c <= b then
    begin
        isScalene := 0;
        exit;
    end;
    if a = b then
    begin
        isScalene := 0;
        exit;
    end;
    if b = c then
    begin
        isScalene := 0;
        exit;
    end;
    if a = c then
    begin
        isScalene := 0;
        exit;
    end;
    isScalene := 1;
end;

var answer: integer;
begin
    answer := isEquilateral(2, 2, 2);
end.
