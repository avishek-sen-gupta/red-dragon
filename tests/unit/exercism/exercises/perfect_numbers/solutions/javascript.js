function classify(n) {
    let total = 0;
    let i = 1;
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

let answer = classify(6);
