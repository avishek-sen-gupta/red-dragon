int nthPrime(int n) {
    int count = 0;
    int candidate = 2;
    while (count < n) {
        int isPrime = 1;
        int divisor = 2;
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

int answer = nthPrime(1);
