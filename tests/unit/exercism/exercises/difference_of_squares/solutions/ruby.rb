def square_of_sum(n)
    total = 0
    i = 1
    while i <= n
        total = total + i
        i = i + 1
    end
    return total * total
end

def sum_of_squares(n)
    total = 0
    i = 1
    while i <= n
        total = total + i * i
        i = i + 1
    end
    return total
end

def difference_of_squares(n)
    return square_of_sum(n) - sum_of_squares(n)
end

answer = difference_of_squares(10)
