object M {
    def hammingDistance(s1: String, s2: String, n: Int): Int = {
        var distance = 0
        var i = 0
        while (i < n) {
            if (s1(i) != s2(i)) {
                distance = distance + 1
            }
            i = i + 1
        }
        return distance
    }

    val answer = hammingDistance("GAGCCTACTAACGGGAT", "CATCGTAATGACGGCCT", 17)
}
