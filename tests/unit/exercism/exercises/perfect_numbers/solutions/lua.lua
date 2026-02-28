function classify(n)
    local total = 0
    local i = 1
    while i < n do
        if n % i == 0 then
            total = total + i
        end
        i = i + 1
    end
    if total == n then
        return "perfect"
    end
    if total > n then
        return "abundant"
    end
    return "deficient"
end

answer = classify(6)
