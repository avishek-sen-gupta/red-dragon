def is_equilateral(a, b, c)
    if a <= 0
        return 0
    end
    if b <= 0
        return 0
    end
    if c <= 0
        return 0
    end
    if a + b <= c
        return 0
    end
    if b + c <= a
        return 0
    end
    if a + c <= b
        return 0
    end
    if a == b
        if b == c
            return 1
        end
    end
    return 0
end

def is_isosceles(a, b, c)
    if a <= 0
        return 0
    end
    if b <= 0
        return 0
    end
    if c <= 0
        return 0
    end
    if a + b <= c
        return 0
    end
    if b + c <= a
        return 0
    end
    if a + c <= b
        return 0
    end
    if a == b
        return 1
    end
    if b == c
        return 1
    end
    if a == c
        return 1
    end
    return 0
end

def is_scalene(a, b, c)
    if a <= 0
        return 0
    end
    if b <= 0
        return 0
    end
    if c <= 0
        return 0
    end
    if a + b <= c
        return 0
    end
    if b + c <= a
        return 0
    end
    if a + c <= b
        return 0
    end
    if a == b
        return 0
    end
    if b == c
        return 0
    end
    if a == c
        return 0
    end
    return 1
end

answer = is_equilateral(2, 2, 2)
