class M {
    static int squareOfSum(int n) {
        int total = 0;
        int i = 1;
        while (i <= n) {
            total = total + i;
            i = i + 1;
        }
        return total * total;
    }

    static int sumOfSquares(int n) {
        int total = 0;
        int i = 1;
        while (i <= n) {
            total = total + i * i;
            i = i + 1;
        }
        return total;
    }

    static int differenceOfSquares(int n) {
        return squareOfSum(n) - sumOfSquares(n);
    }

    static int answer = differenceOfSquares(10);
}
