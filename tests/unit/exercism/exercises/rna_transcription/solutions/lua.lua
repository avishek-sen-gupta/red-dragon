function toRna(dna, n)
    local result = ""
    local i = 0
    while i < n do
        if dna[i] == "G" then
            result = result .. "C"
        end
        if dna[i] == "C" then
            result = result .. "G"
        end
        if dna[i] == "T" then
            result = result .. "A"
        end
        if dna[i] == "A" then
            result = result .. "U"
        end
        i = i + 1
    end
    return result
end

answer = toRna("ACGTGGTCTTAA", 12)
