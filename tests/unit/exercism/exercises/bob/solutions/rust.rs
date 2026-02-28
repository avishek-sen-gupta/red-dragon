fn is_upper_char(c: &str) -> i32 {
    if c == "A" { return 1; }
    if c == "B" { return 1; }
    if c == "C" { return 1; }
    if c == "D" { return 1; }
    if c == "E" { return 1; }
    if c == "F" { return 1; }
    if c == "G" { return 1; }
    if c == "H" { return 1; }
    if c == "I" { return 1; }
    if c == "J" { return 1; }
    if c == "K" { return 1; }
    if c == "L" { return 1; }
    if c == "M" { return 1; }
    if c == "N" { return 1; }
    if c == "O" { return 1; }
    if c == "P" { return 1; }
    if c == "Q" { return 1; }
    if c == "R" { return 1; }
    if c == "S" { return 1; }
    if c == "T" { return 1; }
    if c == "U" { return 1; }
    if c == "V" { return 1; }
    if c == "W" { return 1; }
    if c == "X" { return 1; }
    if c == "Y" { return 1; }
    if c == "Z" { return 1; }
    return 0;
}

fn is_lower_char(c: &str) -> i32 {
    if c == "a" { return 1; }
    if c == "b" { return 1; }
    if c == "c" { return 1; }
    if c == "d" { return 1; }
    if c == "e" { return 1; }
    if c == "f" { return 1; }
    if c == "g" { return 1; }
    if c == "h" { return 1; }
    if c == "i" { return 1; }
    if c == "j" { return 1; }
    if c == "k" { return 1; }
    if c == "l" { return 1; }
    if c == "m" { return 1; }
    if c == "n" { return 1; }
    if c == "o" { return 1; }
    if c == "p" { return 1; }
    if c == "q" { return 1; }
    if c == "r" { return 1; }
    if c == "s" { return 1; }
    if c == "t" { return 1; }
    if c == "u" { return 1; }
    if c == "v" { return 1; }
    if c == "w" { return 1; }
    if c == "x" { return 1; }
    if c == "y" { return 1; }
    if c == "z" { return 1; }
    return 0;
}

fn response(heyBob: &str, n: i32) -> String {
    let mut hasContent: i32 = 0;
    let mut hasUpper: i32 = 0;
    let mut hasLower: i32 = 0;
    let mut lastNonSpace: String = "";
    let mut i: i32 = 0;
    while i < n {
        let c: &str = heyBob[i];
        if c != " " { hasContent = 1; lastNonSpace = c; }
        if is_upper_char(c) == 1 { hasUpper = 1; }
        if is_lower_char(c) == 1 { hasLower = 1; }
        i = i + 1;
    }
    if hasContent == 0 { return "Fine. Be that way!"; }
    let mut isYelling: i32 = 0;
    if hasUpper == 1 { if hasLower == 0 { isYelling = 1; } }
    let mut isQuestion: i32 = 0;
    if lastNonSpace == "?" { isQuestion = 1; }
    if isYelling == 1 {
        if isQuestion == 1 { return "Calm down, I know what I'm doing!"; }
        return "Whoa, chill out!";
    }
    if isQuestion == 1 { return "Sure."; }
    return "Whatever.";
}

let answer = response("Tom-ay-to, tom-aaaah-to.", 24);
