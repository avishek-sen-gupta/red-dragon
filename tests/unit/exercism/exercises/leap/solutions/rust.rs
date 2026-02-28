fn leap_year(year: i32) -> i32 {
    if year % 400 == 0 {
        return 1;
    }
    if year % 100 == 0 {
        return 0;
    }
    if year % 4 == 0 {
        return 1;
    }
    return 0;
}

let answer = leap_year(2000);
