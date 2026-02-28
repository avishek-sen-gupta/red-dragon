function reverseString(s: string, n: number): string {
    let result: string = "";
    let i: number = n - 1;
    while (i >= 0) {
        result = result + s[i];
        i = i - 1;
    }
    return result;
}

let answer: string = reverseString("robot", 5);
