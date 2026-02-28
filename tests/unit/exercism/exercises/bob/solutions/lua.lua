function isUpperChar(c)
    if c == "A" then return 1 end
    if c == "B" then return 1 end
    if c == "C" then return 1 end
    if c == "D" then return 1 end
    if c == "E" then return 1 end
    if c == "F" then return 1 end
    if c == "G" then return 1 end
    if c == "H" then return 1 end
    if c == "I" then return 1 end
    if c == "J" then return 1 end
    if c == "K" then return 1 end
    if c == "L" then return 1 end
    if c == "M" then return 1 end
    if c == "N" then return 1 end
    if c == "O" then return 1 end
    if c == "P" then return 1 end
    if c == "Q" then return 1 end
    if c == "R" then return 1 end
    if c == "S" then return 1 end
    if c == "T" then return 1 end
    if c == "U" then return 1 end
    if c == "V" then return 1 end
    if c == "W" then return 1 end
    if c == "X" then return 1 end
    if c == "Y" then return 1 end
    if c == "Z" then return 1 end
    return 0
end

function isLowerChar(c)
    if c == "a" then return 1 end
    if c == "b" then return 1 end
    if c == "c" then return 1 end
    if c == "d" then return 1 end
    if c == "e" then return 1 end
    if c == "f" then return 1 end
    if c == "g" then return 1 end
    if c == "h" then return 1 end
    if c == "i" then return 1 end
    if c == "j" then return 1 end
    if c == "k" then return 1 end
    if c == "l" then return 1 end
    if c == "m" then return 1 end
    if c == "n" then return 1 end
    if c == "o" then return 1 end
    if c == "p" then return 1 end
    if c == "q" then return 1 end
    if c == "r" then return 1 end
    if c == "s" then return 1 end
    if c == "t" then return 1 end
    if c == "u" then return 1 end
    if c == "v" then return 1 end
    if c == "w" then return 1 end
    if c == "x" then return 1 end
    if c == "y" then return 1 end
    if c == "z" then return 1 end
    return 0
end

function response(heyBob, n)
    local hasContent = 0
    local hasUpper = 0
    local hasLower = 0
    local lastNonSpace = ""
    local i = 0
    while i < n do
        local c = heyBob[i]
        if c ~= " " then
            hasContent = 1
            lastNonSpace = c
        end
        if isUpperChar(c) == 1 then
            hasUpper = 1
        end
        if isLowerChar(c) == 1 then
            hasLower = 1
        end
        i = i + 1
    end
    if hasContent == 0 then
        return "Fine. Be that way!"
    end
    local isYelling = 0
    if hasUpper == 1 then
        if hasLower == 0 then
            isYelling = 1
        end
    end
    local isQuestion = 0
    if lastNonSpace == "?" then
        isQuestion = 1
    end
    if isYelling == 1 then
        if isQuestion == 1 then
            return "Calm down, I know what I'm doing!"
        end
        return "Whoa, chill out!"
    end
    if isQuestion == 1 then
        return "Sure."
    end
    return "Whatever."
end

answer = response("Tom-ay-to, tom-aaaah-to.", 24)
