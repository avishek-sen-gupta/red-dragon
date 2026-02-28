fn hamming_distance(s1: &str, s2: &str, n: i32) -> i32 {
    let distance = 0;
    let i = 0;
    while i < n {
        if s1[i] != s2[i] {
            distance = distance + 1;
        }
        i = i + 1;
    }
    return distance;
}

let answer = hamming_distance("GAGCCTACTAACGGGAT", "CATCGTAATGACGGCCT", 17);
