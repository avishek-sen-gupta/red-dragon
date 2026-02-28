def char_to_digit(c)
    if c == "0"
        return 0
    end
    if c == "1"
        return 1
    end
    if c == "2"
        return 2
    end
    if c == "3"
        return 3
    end
    if c == "4"
        return 4
    end
    if c == "5"
        return 5
    end
    if c == "6"
        return 6
    end
    if c == "7"
        return 7
    end
    if c == "8"
        return 8
    end
    if c == "9"
        return 9
    end
    return -1
end

def is_valid(number, n)
    digitCount = 0
    i = 0
    while i < n
        c = number[i]
        if c == " "
            i = i + 1
            next
        end
        d = char_to_digit(c)
        if d == -1
            return 0
        end
        digitCount = digitCount + 1
        i = i + 1
    end
    if digitCount <= 1
        return 0
    end
    total = 0
    count = 0
    i = n - 1
    while i >= 0
        c = number[i]
        if c == " "
            i = i - 1
            next
        end
        d = char_to_digit(c)
        if count % 2 == 1
            d = d * 2
            if d > 9
                d = d - 9
            end
        end
        total = total + d
        count = count + 1
        i = i - 1
    end
    if total % 10 == 0
        return 1
    end
    return 0
end

answer = is_valid("059", 3)
