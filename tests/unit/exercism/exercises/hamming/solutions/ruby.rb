def hamming_distance(s1, s2, n)
    distance = 0
    i = 0
    while i < n
        if s1[i] != s2[i]
            distance = distance + 1
        end
        i = i + 1
    end
    return distance
end

answer = hamming_distance("GAGCCTACTAACGGGAT", "CATCGTAATGACGGCCT", 17)
