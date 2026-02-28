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

function isPangram(sentence, n)
    local letters = "abcdefghijklmnopqrstuvwxyz"
    local li = 0
    while li < 26 do
        local found = 0
        local si = 0
        while si < n do
            if toLowerChar(sentence[si]) == letters[li] then
                found = 1
                si = n
            end
            si = si + 1
        end
        if found == 0 then
            return 0
        end
        li = li + 1
    end
    return 1
end

answer = isPangram("abcdefghijklmnopqrstuvwxyz", 26)
