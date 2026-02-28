fn square_of_sum(n: i32) -> i32 {
    let mut total: i32 = 0;
    let mut i: i32 = 1;
    while i <= n {
        total = total + i;
        i = i + 1;
    }
    return total * total;
}

fn sum_of_squares(n: i32) -> i32 {
    let mut total: i32 = 0;
    let mut i: i32 = 1;
    while i <= n {
        total = total + i * i;
        i = i + 1;
    }
    return total;
}

fn difference_of_squares(n: i32) -> i32 {
    return square_of_sum(n) - sum_of_squares(n);
}

let answer = difference_of_squares(10);
