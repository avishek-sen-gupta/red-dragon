function collatzSteps(number: number): number {
    let steps: number = 0;
    while (number != 1) {
        if (number % 2 == 0) {
            number = number / 2;
        } else {
            number = number * 3 + 1;
        }
        steps = steps + 1;
    }
    return steps;
}

let answer: number = collatzSteps(16);
