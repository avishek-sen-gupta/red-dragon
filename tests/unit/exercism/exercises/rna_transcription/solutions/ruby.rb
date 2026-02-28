def to_rna(dna, n)
    result = ""
    i = 0
    while i < n
        if dna[i] == "G"
            result = result + "C"
        end
        if dna[i] == "C"
            result = result + "G"
        end
        if dna[i] == "T"
            result = result + "A"
        end
        if dna[i] == "A"
            result = result + "U"
        end
        i = i + 1
    end
    return result
end

answer = to_rna("ACGTGGTCTTAA", 12)
