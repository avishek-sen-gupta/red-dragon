def to_lower_char(c):
    if c == "A":
        return "a"
    if c == "B":
        return "b"
    if c == "C":
        return "c"
    if c == "D":
        return "d"
    if c == "E":
        return "e"
    if c == "F":
        return "f"
    if c == "G":
        return "g"
    if c == "H":
        return "h"
    if c == "I":
        return "i"
    if c == "J":
        return "j"
    if c == "K":
        return "k"
    if c == "L":
        return "l"
    if c == "M":
        return "m"
    if c == "N":
        return "n"
    if c == "O":
        return "o"
    if c == "P":
        return "p"
    if c == "Q":
        return "q"
    if c == "R":
        return "r"
    if c == "S":
        return "s"
    if c == "T":
        return "t"
    if c == "U":
        return "u"
    if c == "V":
        return "v"
    if c == "W":
        return "w"
    if c == "X":
        return "x"
    if c == "Y":
        return "y"
    if c == "Z":
        return "z"
    return c


def is_isogram(word, n):
    i = 0
    while i < n:
        if word[i] == " ":
            i = i + 1
            continue
        if word[i] == "-":
            i = i + 1
            continue
        j = i + 1
        while j < n:
            if word[j] == " ":
                j = j + 1
                continue
            if word[j] == "-":
                j = j + 1
                continue
            if to_lower_char(word[i]) == to_lower_char(word[j]):
                return 0
            j = j + 1
        i = i + 1
    return 1


answer = is_isogram("isogram", 7)
