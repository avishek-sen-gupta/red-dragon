fun reverseString(s: String, n: Int): String {
    var result = ""
    var i = n - 1
    while (i >= 0) {
        result = result + s[i]
        i = i - 1
    }
    return result
}

val answer = reverseString("robot", 5)
