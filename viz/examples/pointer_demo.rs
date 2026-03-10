let mut x = 42;
let ptr = &mut x;
*ptr = 99;
let answer = x;
