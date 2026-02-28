def char_to_digit(c):
    if c == "0":
        return 0
    if c == "1":
        return 1
    if c == "2":
        return 2
    if c == "3":
        return 3
    if c == "4":
        return 4
    if c == "5":
        return 5
    if c == "6":
        return 6
    if c == "7":
        return 7
    if c == "8":
        return 8
    if c == "9":
        return 9
    return -1


def is_valid(number, n):
    digitCount = 0
    i = 0
    while i < n:
        c = number[i]
        if c == " ":
            i = i + 1
            continue
        d = char_to_digit(c)
        if d == -1:
            return 0
        digitCount = digitCount + 1
        i = i + 1
    if digitCount <= 1:
        return 0
    total = 0
    count = 0
    i = n - 1
    while i >= 0:
        c = number[i]
        if c == " ":
            i = i - 1
            continue
        d = char_to_digit(c)
        if count % 2 == 1:
            d = d * 2
            if d > 9:
                d = d - 9
        total = total + d
        count = count + 1
        i = i - 1
    if total % 10 == 0:
        return 1
    return 0


answer = is_valid("059", 3)
