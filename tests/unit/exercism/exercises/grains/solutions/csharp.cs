class M {
    static int square(int n) {
        int result = 1;
        int i = 1;
        while (i < n) {
            result = result * 2;
            i = i + 1;
        }
        return result;
    }

    static int total() {
        int result = 0;
        int power = 1;
        int i = 1;
        while (i <= 64) {
            result = result + power;
            power = power * 2;
            i = i + 1;
        }
        return result;
    }

    static int answer = square(1);
}
