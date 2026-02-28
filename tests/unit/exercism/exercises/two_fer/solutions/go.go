package main

func twoFer(name string) string {
    return "One for " + name + ", one for me."
}

func main() {
    answer := twoFer("Alice")
    _ = answer
}
