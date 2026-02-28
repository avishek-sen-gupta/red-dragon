package main

func nthPrime(n int) int {
    count := 0
    candidate := 2
    for count < n {
        isPrime := 1
        divisor := 2
        for divisor * divisor <= candidate {
            if candidate % divisor == 0 {
                isPrime = 0
            }
            divisor = divisor + 1
        }
        if isPrime == 1 {
            count = count + 1
        }
        if count < n {
            candidate = candidate + 1
        }
    }
    return candidate
}

func main() {
    answer := nthPrime(1)
    _ = answer
}
