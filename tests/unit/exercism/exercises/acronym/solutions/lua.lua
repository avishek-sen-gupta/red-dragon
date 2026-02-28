function toUpperChar(c)
    if c == "a" then return "A" end
    if c == "b" then return "B" end
    if c == "c" then return "C" end
    if c == "d" then return "D" end
    if c == "e" then return "E" end
    if c == "f" then return "F" end
    if c == "g" then return "G" end
    if c == "h" then return "H" end
    if c == "i" then return "I" end
    if c == "j" then return "J" end
    if c == "k" then return "K" end
    if c == "l" then return "L" end
    if c == "m" then return "M" end
    if c == "n" then return "N" end
    if c == "o" then return "O" end
    if c == "p" then return "P" end
    if c == "q" then return "Q" end
    if c == "r" then return "R" end
    if c == "s" then return "S" end
    if c == "t" then return "T" end
    if c == "u" then return "U" end
    if c == "v" then return "V" end
    if c == "w" then return "W" end
    if c == "x" then return "X" end
    if c == "y" then return "Y" end
    if c == "z" then return "Z" end
    return c
end

function abbreviate(phrase, n)
    local result = ""
    local atWordStart = 1
    local i = 0
    while i < n do
        local c = phrase[i]
        if c == " " then
            atWordStart = 1
            i = i + 1
        elseif c == "-" then
            atWordStart = 1
            i = i + 1
        elseif c == "_" then
            atWordStart = 1
            i = i + 1
        else
            if atWordStart == 1 then
                result = result .. toUpperChar(c)
                atWordStart = 0
            end
            i = i + 1
        end
    end
    return result
end

answer = abbreviate("Portable Network Graphics", 25)
