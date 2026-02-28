function square(n)
    local result = 1
    local i = 1
    while i < n do
        result = result * 2
        i = i + 1
    end
    return result
end

function total()
    local result = 0
    local power = 1
    local i = 1
    while i <= 64 do
        result = result + power
        power = power * 2
        i = i + 1
    end
    return result
end

answer = square(1)
