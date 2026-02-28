fun nthPrime(n: Int): Int {
    var count: Int = 0
    var candidate: Int = 2
    while (count < n) {
        var isPrime: Int = 1
        var divisor: Int = 2
        while (divisor * divisor <= candidate) {
            if (candidate % divisor == 0) {
                isPrime = 0
            }
            divisor = divisor + 1
        }
        if (isPrime == 1) {
            count = count + 1
        }
        if (count < n) {
            candidate = candidate + 1
        }
    }
    return candidate
}

val answer = nthPrime(1)
