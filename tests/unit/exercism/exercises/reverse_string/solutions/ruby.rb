def reverse_string(s, n)
    result = ""
    i = n - 1
    while i >= 0
        result = result + s[i]
        i = i - 1
    end
    return result
end

answer = reverse_string("robot", 5)
