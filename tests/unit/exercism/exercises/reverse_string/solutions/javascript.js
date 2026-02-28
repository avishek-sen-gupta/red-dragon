function reverseString(s, n) {
    let result = "";
    let i = n - 1;
    while (i >= 0) {
        result = result + s[i];
        i = i - 1;
    }
    return result;
}

let answer = reverseString("robot", 5);
