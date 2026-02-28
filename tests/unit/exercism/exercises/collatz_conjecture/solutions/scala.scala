object M {
    def collatzSteps(number: Int): Int = {
        var n: Int = number
        var steps: Int = 0
        while (n != 1) {
            if (n % 2 == 0) {
                n = n / 2
            } else {
                n = n * 3 + 1
            }
            steps = steps + 1
        }
        return steps
    }

    val answer = collatzSteps(16)
}
