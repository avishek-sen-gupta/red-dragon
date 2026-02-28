function nthPrime(n) {
    let count = 0;
    let candidate = 2;
    while (count < n) {
        let isPrime = 1;
        let divisor = 2;
        while (divisor * divisor <= candidate) {
            if (candidate % divisor == 0) {
                isPrime = 0;
            }
            divisor = divisor + 1;
        }
        if (isPrime == 1) {
            count = count + 1;
        }
        if (count < n) {
            candidate = candidate + 1;
        }
    }
    return candidate;
}

let answer = nthPrime(1);
