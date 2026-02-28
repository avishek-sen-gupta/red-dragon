def to_rna(dna, n):
    result = ""
    i = 0
    while i < n:
        if dna[i] == "G":
            result = result + "C"
        if dna[i] == "C":
            result = result + "G"
        if dna[i] == "T":
            result = result + "A"
        if dna[i] == "A":
            result = result + "U"
        i = i + 1
    return result


answer = to_rna("ACGTGGTCTTAA", 12)
