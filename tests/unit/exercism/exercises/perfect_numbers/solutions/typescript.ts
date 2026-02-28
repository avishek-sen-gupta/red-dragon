function classify(n: number): string {
    let total: number = 0;
    let i: number = 1;
    while (i < n) {
        if (n % i == 0) {
            total = total + i;
        }
        i = i + 1;
    }
    if (total == n) {
        return "perfect";
    }
    if (total > n) {
        return "abundant";
    }
    return "deficient";
}

let answer: string = classify(6);
