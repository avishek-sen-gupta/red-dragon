function toRna(dna: string, n: number): string {
    let result: string = "";
    let i: number = 0;
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

let answer: string = toRna("ACGTGGTCTTAA", 12);
