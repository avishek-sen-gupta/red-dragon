package main

func collatzSteps(number int) int {
    steps := 0
    for number != 1 {
        if number % 2 == 0 {
            number = number / 2
        } else {
            number = number * 3 + 1
        }
        steps = steps + 1
    }
    return steps
}

func main() {
    answer := collatzSteps(16)
    _ = answer
}
