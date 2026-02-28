object M {
    def squareOfSum(n: Int): Int = {
        var total: Int = 0
        var i: Int = 1
        while (i <= n) {
            total = total + i
            i = i + 1
        }
        return total * total
    }

    def sumOfSquares(n: Int): Int = {
        var total: Int = 0
        var i: Int = 1
        while (i <= n) {
            total = total + (i * i)
            i = i + 1
        }
        return total
    }

    def differenceOfSquares(n: Int): Int = {
        return squareOfSum(n) - sumOfSquares(n)
    }

    val answer = differenceOfSquares(10)
}
