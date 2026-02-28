function squareOfSum(n: number): number {
    let total: number = 0;
    let i: number = 1;
    while (i <= n) {
        total = total + i;
        i = i + 1;
    }
    return total * total;
}

function sumOfSquares(n: number): number {
    let total: number = 0;
    let i: number = 1;
    while (i <= n) {
        total = total + i * i;
        i = i + 1;
    }
    return total;
}

function differenceOfSquares(n: number): number {
    return squareOfSum(n) - sumOfSquares(n);
}

let answer: number = differenceOfSquares(10);
