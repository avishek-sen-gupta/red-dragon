package main

func hammingDistance(s1 string, s2 string, n int) int {
    distance := 0
    i := 0
    for i < n {
        if s1[i] != s2[i] {
            distance = distance + 1
        }
        i = i + 1
    }
    return distance
}

func main() {
    answer := hammingDistance("GAGCCTACTAACGGGAT", "CATCGTAATGACGGCCT", 17)
    _ = answer
}
