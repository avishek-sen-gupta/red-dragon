package main

func square(n int) int {
    result := 1
    i := 1
    for i < n {
        result = result * 2
        i = i + 1
    }
    return result
}

func total() int {
    result := 0
    power := 1
    i := 1
    for i <= 64 {
        result = result + power
        power = power * 2
        i = i + 1
    }
    return result
}

func main() {
    answer := square(1)
    _ = answer
}
