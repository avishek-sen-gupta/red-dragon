package main

func reverseString(s string, n int) string {
    result := ""
    i := n - 1
    for i >= 0 {
        result = result + s[i]
        i = i - 1
    }
    return result
}

func main() {
    answer := reverseString("robot", 5)
    _ = answer
}
