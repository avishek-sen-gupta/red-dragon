function hammingDistance(s1, s2, n)
    local distance = 0
    local i = 0
    while i < n do
        if s1[i] ~= s2[i] then
            distance = distance + 1
        end
        i = i + 1
    end
    return distance
end

answer = hammingDistance("GAGCCTACTAACGGGAT", "CATCGTAATGACGGCCT", 17)
