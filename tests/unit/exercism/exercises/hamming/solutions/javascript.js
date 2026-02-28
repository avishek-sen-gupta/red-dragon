function hammingDistance(s1, s2, n) {
    let distance = 0;
    let i = 0;
    while (i < n) {
        if (s1[i] != s2[i]) {
            distance = distance + 1;
        }
        i = i + 1;
    }
    return distance;
}

let answer = hammingDistance("GAGCCTACTAACGGGAT", "CATCGTAATGACGGCCT", 17);
