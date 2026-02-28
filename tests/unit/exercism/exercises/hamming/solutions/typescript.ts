function hammingDistance(s1: string, s2: string, n: number): number {
    let distance: number = 0;
    let i: number = 0;
    while (i < n) {
        if (s1[i] != s2[i]) {
            distance = distance + 1;
        }
        i = i + 1;
    }
    return distance;
}

let answer: number = hammingDistance("GAGCCTACTAACGGGAT", "CATCGTAATGACGGCCT", 17);
