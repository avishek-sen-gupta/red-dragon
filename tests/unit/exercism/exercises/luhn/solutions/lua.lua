function charToDigit(c)
    if c == "0" then return 0 end
    if c == "1" then return 1 end
    if c == "2" then return 2 end
    if c == "3" then return 3 end
    if c == "4" then return 4 end
    if c == "5" then return 5 end
    if c == "6" then return 6 end
    if c == "7" then return 7 end
    if c == "8" then return 8 end
    if c == "9" then return 9 end
    return -1
end

function isValid(number, n)
    local digitCount = 0
    local i = 0
    while i < n do
        local c = number[i]
        if c == " " then
            i = i + 1
        else
            local d = charToDigit(c)
            if d == -1 then
                return 0
            end
            digitCount = digitCount + 1
            i = i + 1
        end
    end
    if digitCount <= 1 then
        return 0
    end
    local total = 0
    local count = 0
    i = n - 1
    while i >= 0 do
        local c = number[i]
        if c == " " then
            i = i - 1
        else
            local d = charToDigit(c)
            if count % 2 == 1 then
                d = d * 2
                if d > 9 then
                    d = d - 9
                end
            end
            total = total + d
            count = count + 1
            i = i - 1
        end
    end
    if total % 10 == 0 then
        return 1
    end
    return 0
end

answer = isValid("059", 3)
