def square(n)
    result = 1
    i = 1
    while i < n
        result = result * 2
        i = i + 1
    end
    return result
end

def total()
    result = 0
    power = 1
    i = 1
    while i <= 64
        result = result + power
        power = power * 2
        i = i + 1
    end
    return result
end

answer = square(1)
