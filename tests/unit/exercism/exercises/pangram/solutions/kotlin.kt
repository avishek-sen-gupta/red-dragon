fun toLowerChar(c: String): String {
    if (c == "A") { return "a" }
    if (c == "B") { return "b" }
    if (c == "C") { return "c" }
    if (c == "D") { return "d" }
    if (c == "E") { return "e" }
    if (c == "F") { return "f" }
    if (c == "G") { return "g" }
    if (c == "H") { return "h" }
    if (c == "I") { return "i" }
    if (c == "J") { return "j" }
    if (c == "K") { return "k" }
    if (c == "L") { return "l" }
    if (c == "M") { return "m" }
    if (c == "N") { return "n" }
    if (c == "O") { return "o" }
    if (c == "P") { return "p" }
    if (c == "Q") { return "q" }
    if (c == "R") { return "r" }
    if (c == "S") { return "s" }
    if (c == "T") { return "t" }
    if (c == "U") { return "u" }
    if (c == "V") { return "v" }
    if (c == "W") { return "w" }
    if (c == "X") { return "x" }
    if (c == "Y") { return "y" }
    if (c == "Z") { return "z" }
    return c
}

fun isPangram(sentence: String, n: Int): Int {
    val letters: String = "abcdefghijklmnopqrstuvwxyz"
    var li: Int = 0
    while (li < 26) {
        var found: Int = 0
        var si: Int = 0
        while (si < n) {
            if (toLowerChar(sentence[si]) == letters[li]) {
                found = 1
                si = n
            }
            si = si + 1
        }
        if (found == 0) {
            return 0
        }
        li = li + 1
    }
    return 1
}

val answer = isPangram("abcdefghijklmnopqrstuvwxyz", 26)
