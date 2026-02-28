package main

func classify(n int) string {
    total := 0
    i := 1
    for i < n {
        if n % i == 0 {
            total = total + i
        }
        i = i + 1
    }
    if total == n {
        return "perfect"
    }
    if total > n {
        return "abundant"
    }
    return "deficient"
}

func main() {
    answer := classify(6)
    _ = answer
}
