fun collatzSteps(number: Int): Int {
    var number: Int = number
    var steps: Int = 0
    while (number != 1) {
        if (number % 2 == 0) {
            number = number / 2
        } else {
            number = number * 3 + 1
        }
        steps = steps + 1
    }
    return steps
}

val answer = collatzSteps(16)
