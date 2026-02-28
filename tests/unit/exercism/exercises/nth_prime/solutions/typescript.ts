function nthPrime(n: number): number {
    let count: number = 0;
    let candidate: number = 2;
    while (count < n) {
        let isPrime: number = 1;
        let divisor: number = 2;
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

let answer: number = nthPrime(1);
