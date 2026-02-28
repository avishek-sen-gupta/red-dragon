function square(n) {
    let result = 1;
    let i = 1;
    while (i < n) {
        result = result * 2;
        i = i + 1;
    }
    return result;
}

function total() {
    let result = 0;
    let power = 1;
    let i = 1;
    while (i <= 64) {
        result = result + power;
        power = power * 2;
        i = i + 1;
    }
    return result;
}

let answer = square(1);
