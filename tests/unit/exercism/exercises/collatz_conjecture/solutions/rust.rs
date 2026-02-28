fn collatz_steps(number: i32) -> i32 {
    let mut number: i32 = number;
    let mut steps: i32 = 0;
    while number != 1 {
        if number % 2 == 0 {
            number = number / 2;
        } else {
            number = number * 3 + 1;
        }
        steps = steps + 1;
    }
    return steps;
}

let answer = collatz_steps(16);
