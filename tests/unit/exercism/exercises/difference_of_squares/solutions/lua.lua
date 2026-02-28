function squareOfSum(n)
    local total = 0
    local i = 1
    while i <= n do
        total = total + i
        i = i + 1
    end
    return total * total
end

function sumOfSquares(n)
    local total = 0
    local i = 1
    while i <= n do
        total = total + i * i
        i = i + 1
    end
    return total
end

function differenceOfSquares(n)
    return squareOfSum(n) - sumOfSquares(n)
end

answer = differenceOfSquares(10)
