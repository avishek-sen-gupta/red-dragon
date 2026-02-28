function square(n: number): number {
    let result: number = 1;
    let i: number = 1;
    while (i < n) {
        result = result * 2;
        i = i + 1;
    }
    return result;
}

function total(): number {
    let result: number = 0;
    let power: number = 1;
    let i: number = 1;
    while (i <= 64) {
        result = result + power;
        power = power * 2;
        i = i + 1;
    }
    return result;
}

let answer: number = square(1);
