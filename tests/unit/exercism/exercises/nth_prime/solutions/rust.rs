fn nth_prime(n: i32) -> i32 {
    let mut count: i32 = 0;
    let mut candidate: i32 = 2;
    while count < n {
        let mut is_prime: i32 = 1;
        let mut divisor: i32 = 2;
        while divisor * divisor <= candidate {
            if candidate % divisor == 0 {
                is_prime = 0;
            }
            divisor = divisor + 1;
        }
        if is_prime == 1 {
            count = count + 1;
        }
        if count < n {
            candidate = candidate + 1;
        }
    }
    return candidate;
}

let answer = nth_prime(1);
