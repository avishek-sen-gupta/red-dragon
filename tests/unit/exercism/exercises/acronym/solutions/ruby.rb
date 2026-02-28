def to_upper_char(c)
    if c == "a"
        return "A"
    end
    if c == "b"
        return "B"
    end
    if c == "c"
        return "C"
    end
    if c == "d"
        return "D"
    end
    if c == "e"
        return "E"
    end
    if c == "f"
        return "F"
    end
    if c == "g"
        return "G"
    end
    if c == "h"
        return "H"
    end
    if c == "i"
        return "I"
    end
    if c == "j"
        return "J"
    end
    if c == "k"
        return "K"
    end
    if c == "l"
        return "L"
    end
    if c == "m"
        return "M"
    end
    if c == "n"
        return "N"
    end
    if c == "o"
        return "O"
    end
    if c == "p"
        return "P"
    end
    if c == "q"
        return "Q"
    end
    if c == "r"
        return "R"
    end
    if c == "s"
        return "S"
    end
    if c == "t"
        return "T"
    end
    if c == "u"
        return "U"
    end
    if c == "v"
        return "V"
    end
    if c == "w"
        return "W"
    end
    if c == "x"
        return "X"
    end
    if c == "y"
        return "Y"
    end
    if c == "z"
        return "Z"
    end
    return c
end

def abbreviate(phrase, n)
    result = ""
    atWordStart = 1
    i = 0
    while i < n
        c = phrase[i]
        if c == " "
            atWordStart = 1
            i = i + 1
            next
        end
        if c == "-"
            atWordStart = 1
            i = i + 1
            next
        end
        if c == "_"
            atWordStart = 1
            i = i + 1
            next
        end
        if atWordStart == 1
            result = result + to_upper_char(c)
            atWordStart = 0
        end
        i = i + 1
    end
    return result
end

answer = abbreviate("Portable Network Graphics", 25)
