def classify(n)
    total = 0
    i = 1
    while i < n
        if n % i == 0
            total = total + i
        end
        i = i + 1
    end
    if total == n
        return "perfect"
    end
    if total > n
        return "abundant"
    end
    return "deficient"
end

answer = classify(6)
