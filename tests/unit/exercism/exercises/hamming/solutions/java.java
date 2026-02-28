class M {
    static int hammingDistance(String s1, String s2, int n) {
        int distance = 0;
        int i = 0;
        while (i < n) {
            if (s1[i] != s2[i]) {
                distance = distance + 1;
            }
            i = i + 1;
        }
        return distance;
    }

    static int answer = hammingDistance("GAGCCTACTAACGGGAT", "CATCGTAATGACGGCCT", 17);
}
