function isEquilateral(a, b, c)
    if a <= 0 then
        return 0
    end
    if b <= 0 then
        return 0
    end
    if c <= 0 then
        return 0
    end
    if a + b <= c then
        return 0
    end
    if b + c <= a then
        return 0
    end
    if a + c <= b then
        return 0
    end
    if a == b then
        if b == c then
            return 1
        end
    end
    return 0
end

function isIsosceles(a, b, c)
    if a <= 0 then
        return 0
    end
    if b <= 0 then
        return 0
    end
    if c <= 0 then
        return 0
    end
    if a + b <= c then
        return 0
    end
    if b + c <= a then
        return 0
    end
    if a + c <= b then
        return 0
    end
    if a == b then
        return 1
    end
    if b == c then
        return 1
    end
    if a == c then
        return 1
    end
    return 0
end

function isScalene(a, b, c)
    if a <= 0 then
        return 0
    end
    if b <= 0 then
        return 0
    end
    if c <= 0 then
        return 0
    end
    if a + b <= c then
        return 0
    end
    if b + c <= a then
        return 0
    end
    if a + c <= b then
        return 0
    end
    if a == b then
        return 0
    end
    if b == c then
        return 0
    end
    if a == c then
        return 0
    end
    return 1
end

answer = isEquilateral(2, 2, 2)
