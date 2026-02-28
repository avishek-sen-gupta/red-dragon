function squareOfSum(n) {
    let total = 0;
    let i = 1;
    while (i <= n) {
        total = total + i;
        i = i + 1;
    }
    return total * total;
}

function sumOfSquares(n) {
    let total = 0;
    let i = 1;
    while (i <= n) {
        total = total + i * i;
        i = i + 1;
    }
    return total;
}

function differenceOfSquares(n) {
    return squareOfSum(n) - sumOfSquares(n);
}

let answer = differenceOfSquares(10);
