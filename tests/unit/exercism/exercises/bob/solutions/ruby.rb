def is_upper_char(c)
    if c == "A"
        return 1
    end
    if c == "B"
        return 1
    end
    if c == "C"
        return 1
    end
    if c == "D"
        return 1
    end
    if c == "E"
        return 1
    end
    if c == "F"
        return 1
    end
    if c == "G"
        return 1
    end
    if c == "H"
        return 1
    end
    if c == "I"
        return 1
    end
    if c == "J"
        return 1
    end
    if c == "K"
        return 1
    end
    if c == "L"
        return 1
    end
    if c == "M"
        return 1
    end
    if c == "N"
        return 1
    end
    if c == "O"
        return 1
    end
    if c == "P"
        return 1
    end
    if c == "Q"
        return 1
    end
    if c == "R"
        return 1
    end
    if c == "S"
        return 1
    end
    if c == "T"
        return 1
    end
    if c == "U"
        return 1
    end
    if c == "V"
        return 1
    end
    if c == "W"
        return 1
    end
    if c == "X"
        return 1
    end
    if c == "Y"
        return 1
    end
    if c == "Z"
        return 1
    end
    return 0
end

def is_lower_char(c)
    if c == "a"
        return 1
    end
    if c == "b"
        return 1
    end
    if c == "c"
        return 1
    end
    if c == "d"
        return 1
    end
    if c == "e"
        return 1
    end
    if c == "f"
        return 1
    end
    if c == "g"
        return 1
    end
    if c == "h"
        return 1
    end
    if c == "i"
        return 1
    end
    if c == "j"
        return 1
    end
    if c == "k"
        return 1
    end
    if c == "l"
        return 1
    end
    if c == "m"
        return 1
    end
    if c == "n"
        return 1
    end
    if c == "o"
        return 1
    end
    if c == "p"
        return 1
    end
    if c == "q"
        return 1
    end
    if c == "r"
        return 1
    end
    if c == "s"
        return 1
    end
    if c == "t"
        return 1
    end
    if c == "u"
        return 1
    end
    if c == "v"
        return 1
    end
    if c == "w"
        return 1
    end
    if c == "x"
        return 1
    end
    if c == "y"
        return 1
    end
    if c == "z"
        return 1
    end
    return 0
end

def response(heyBob, n)
    hasContent = 0
    hasUpper = 0
    hasLower = 0
    lastNonSpace = ""
    i = 0
    while i < n
        c = heyBob[i]
        if c != " "
            hasContent = 1
            lastNonSpace = c
        end
        if is_upper_char(c) == 1
            hasUpper = 1
        end
        if is_lower_char(c) == 1
            hasLower = 1
        end
        i = i + 1
    end
    if hasContent == 0
        return "Fine. Be that way!"
    end
    isYelling = 0
    if hasUpper == 1
        if hasLower == 0
            isYelling = 1
        end
    end
    isQuestion = 0
    if lastNonSpace == "?"
        isQuestion = 1
    end
    if isYelling == 1
        if isQuestion == 1
            return "Calm down, I know what I'm doing!"
        end
        return "Whoa, chill out!"
    end
    if isQuestion == 1
        return "Sure."
    end
    return "Whatever."
end

answer = response("Tom-ay-to, tom-aaaah-to.", 24)
