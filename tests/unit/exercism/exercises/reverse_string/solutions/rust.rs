fn reverse_string(s: &str, n: i32) -> String {
    let result = "";
    let i = n - 1;
    while i >= 0 {
        result = result + s[i];
        i = i - 1;
    }
    return result;
}

let answer = reverse_string("robot", 5);
