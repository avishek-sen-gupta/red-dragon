class M {
    static String toRna(String dna, int n) {
        String result = "";
        int i = 0;
        while (i < n) {
            if (dna[i] == "G") {
                result = result + "C";
            }
            if (dna[i] == "C") {
                result = result + "G";
            }
            if (dna[i] == "T") {
                result = result + "A";
            }
            if (dna[i] == "A") {
                result = result + "U";
            }
            i = i + 1;
        }
        return result;
    }

    static String answer = toRna("ACGTGGTCTTAA", 12);
}
