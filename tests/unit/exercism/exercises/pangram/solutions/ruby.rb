def to_lower_char(c)
    if c == "A"
        return "a"
    end
    if c == "B"
        return "b"
    end
    if c == "C"
        return "c"
    end
    if c == "D"
        return "d"
    end
    if c == "E"
        return "e"
    end
    if c == "F"
        return "f"
    end
    if c == "G"
        return "g"
    end
    if c == "H"
        return "h"
    end
    if c == "I"
        return "i"
    end
    if c == "J"
        return "j"
    end
    if c == "K"
        return "k"
    end
    if c == "L"
        return "l"
    end
    if c == "M"
        return "m"
    end
    if c == "N"
        return "n"
    end
    if c == "O"
        return "o"
    end
    if c == "P"
        return "p"
    end
    if c == "Q"
        return "q"
    end
    if c == "R"
        return "r"
    end
    if c == "S"
        return "s"
    end
    if c == "T"
        return "t"
    end
    if c == "U"
        return "u"
    end
    if c == "V"
        return "v"
    end
    if c == "W"
        return "w"
    end
    if c == "X"
        return "x"
    end
    if c == "Y"
        return "y"
    end
    if c == "Z"
        return "z"
    end
    return c
end

def is_pangram(sentence, n)
    letters = "abcdefghijklmnopqrstuvwxyz"
    li = 0
    while li < 26
        found = 0
        si = 0
        while si < n
            if to_lower_char(sentence[si]) == letters[li]
                found = 1
                si = n
            end
            si = si + 1
        end
        if found == 0
            return 0
        end
        li = li + 1
    end
    return 1
end

answer = is_pangram("abcdefghijklmnopqrstuvwxyz", 26)
