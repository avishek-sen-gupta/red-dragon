int isEquilateral(int a, int b, int c) {
    if (a <= 0) {
        return 0;
    }
    if (b <= 0) {
        return 0;
    }
    if (c <= 0) {
        return 0;
    }
    if (a + b <= c) {
        return 0;
    }
    if (b + c <= a) {
        return 0;
    }
    if (a + c <= b) {
        return 0;
    }
    if (a == b) {
        if (b == c) {
            return 1;
        }
    }
    return 0;
}

int isIsosceles(int a, int b, int c) {
    if (a <= 0) {
        return 0;
    }
    if (b <= 0) {
        return 0;
    }
    if (c <= 0) {
        return 0;
    }
    if (a + b <= c) {
        return 0;
    }
    if (b + c <= a) {
        return 0;
    }
    if (a + c <= b) {
        return 0;
    }
    if (a == b) {
        return 1;
    }
    if (b == c) {
        return 1;
    }
    if (a == c) {
        return 1;
    }
    return 0;
}

int isScalene(int a, int b, int c) {
    if (a <= 0) {
        return 0;
    }
    if (b <= 0) {
        return 0;
    }
    if (c <= 0) {
        return 0;
    }
    if (a + b <= c) {
        return 0;
    }
    if (b + c <= a) {
        return 0;
    }
    if (a + c <= b) {
        return 0;
    }
    if (a == b) {
        return 0;
    }
    if (b == c) {
        return 0;
    }
    if (a == c) {
        return 0;
    }
    return 1;
}

int answer = isEquilateral(2, 2, 2);
