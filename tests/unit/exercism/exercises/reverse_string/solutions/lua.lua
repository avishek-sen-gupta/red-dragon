function reverseString(s, n)
    local result = ""
    local i = n - 1
    while i >= 0 do
        result = result .. s[i]
        i = i - 1
    end
    return result
end

answer = reverseString("robot", 5)
