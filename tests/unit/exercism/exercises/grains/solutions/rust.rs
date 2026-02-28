fn square(n: i32) -> i32 {
    let mut result: i32 = 1;
    let mut i: i32 = 1;
    while i < n {
        result = result * 2;
        i = i + 1;
    }
    return result;
}

fn total() -> i32 {
    let mut result: i32 = 0;
    let mut power: i32 = 1;
    let mut i: i32 = 1;
    while i <= 64 {
        result = result + power;
        power = power * 2;
        i = i + 1;
    }
    return result;
}

let answer = square(1);
