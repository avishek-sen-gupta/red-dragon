int squareOfSum(int n) {
    int total = 0;
    int i = 1;
    while (i <= n) {
        total = total + i;
        i = i + 1;
    }
    return total * total;
}

int sumOfSquares(int n) {
    int total = 0;
    int i = 1;
    while (i <= n) {
        total = total + i * i;
        i = i + 1;
    }
    return total;
}

int differenceOfSquares(int n) {
    return squareOfSum(n) - sumOfSquares(n);
}

int answer = differenceOfSquares(10);
