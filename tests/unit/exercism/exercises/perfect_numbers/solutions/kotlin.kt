fun classify(n: Int): String {
    var total = 0
    var i = 1
    while (i < n) {
        if (n % i == 0) {
            total = total + i
        }
        i = i + 1
    }
    if (total == n) {
        return "perfect"
    }
    if (total > n) {
        return "abundant"
    }
    return "deficient"
}

val answer = classify(6)
