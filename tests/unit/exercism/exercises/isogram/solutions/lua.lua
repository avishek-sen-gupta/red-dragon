function toLowerChar(c)
    if c == "A" then return "a" end
    if c == "B" then return "b" end
    if c == "C" then return "c" end
    if c == "D" then return "d" end
    if c == "E" then return "e" end
    if c == "F" then return "f" end
    if c == "G" then return "g" end
    if c == "H" then return "h" end
    if c == "I" then return "i" end
    if c == "J" then return "j" end
    if c == "K" then return "k" end
    if c == "L" then return "l" end
    if c == "M" then return "m" end
    if c == "N" then return "n" end
    if c == "O" then return "o" end
    if c == "P" then return "p" end
    if c == "Q" then return "q" end
    if c == "R" then return "r" end
    if c == "S" then return "s" end
    if c == "T" then return "t" end
    if c == "U" then return "u" end
    if c == "V" then return "v" end
    if c == "W" then return "w" end
    if c == "X" then return "x" end
    if c == "Y" then return "y" end
    if c == "Z" then return "z" end
    return c
end

function isIsogram(word, n)
    local i = 0
    while i < n do
        if word[i] == " " then i = i + 1 end
        if word[i] == "-" then i = i + 1 end
        local j = i + 1
        while j < n do
            if word[j] == " " then j = j + 1 end
            if word[j] == "-" then j = j + 1 end
            if toLowerChar(word[i]) == toLowerChar(word[j]) then
                return 0
            end
            j = j + 1
        end
        i = i + 1
    end
    return 1
end

answer = isIsogram("isogram", 7)
