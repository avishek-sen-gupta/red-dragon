package main

func toRna(dna string, n int) string {
    result := ""
    i := 0
    for i < n {
        if dna[i] == "G" {
            result = result + "C"
        }
        if dna[i] == "C" {
            result = result + "G"
        }
        if dna[i] == "T" {
            result = result + "A"
        }
        if dna[i] == "A" {
            result = result + "U"
        }
        i = i + 1
    }
    return result
}

func main() {
    answer := toRna("ACGTGGTCTTAA", 12)
    _ = answer
}
