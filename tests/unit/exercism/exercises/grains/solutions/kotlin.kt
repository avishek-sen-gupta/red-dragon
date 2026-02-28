fun square(n: Int): Int {
    var result: Int = 1
    var i: Int = 1
    while (i < n) {
        result = result * 2
        i = i + 1
    }
    return result
}

fun total(): Int {
    var result: Int = 0
    var power: Int = 1
    var i: Int = 1
    while (i <= 64) {
        result = result + power
        power = power * 2
        i = i + 1
    }
    return result
}

val answer = square(1)
