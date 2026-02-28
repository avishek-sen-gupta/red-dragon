package main

func squareOfSum(n int) int {
    total := 0
    i := 1
    for i <= n {
        total = total + i
        i = i + 1
    }
    return total * total
}

func sumOfSquares(n int) int {
    total := 0
    i := 1
    for i <= n {
        total = total + i * i
        i = i + 1
    }
    return total
}

func differenceOfSquares(n int) int {
    return squareOfSum(n) - sumOfSquares(n)
}

func main() {
    answer := differenceOfSquares(10)
    _ = answer
}
