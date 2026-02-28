fn char_to_digit(c: &str) -> i32 {
    if c == "0" { return 0; }
    if c == "1" { return 1; }
    if c == "2" { return 2; }
    if c == "3" { return 3; }
    if c == "4" { return 4; }
    if c == "5" { return 5; }
    if c == "6" { return 6; }
    if c == "7" { return 7; }
    if c == "8" { return 8; }
    if c == "9" { return 9; }
    return -1;
}

fn is_valid(number: &str, n: i32) -> i32 {
    let mut digitCount: i32 = 0;
    let mut i: i32 = 0;
    while i < n {
        let c: &str = number[i];
        if c == " " { i = i + 1; continue; }
        let d: i32 = char_to_digit(c);
        if d == -1 { return 0; }
        digitCount = digitCount + 1;
        i = i + 1;
    }
    if digitCount <= 1 { return 0; }
    let mut total: i32 = 0;
    let mut count: i32 = 0;
    i = n - 1;
    while i >= 0 {
        let c: &str = number[i];
        if c == " " { i = i - 1; continue; }
        let mut d: i32 = char_to_digit(c);
        if count % 2 == 1 {
            d = d * 2;
            if d > 9 { d = d - 9; }
        }
        total = total + d;
        count = count + 1;
        i = i - 1;
    }
    if total % 10 == 0 { return 1; }
    return 0;
}

let answer = is_valid("059", 3);
