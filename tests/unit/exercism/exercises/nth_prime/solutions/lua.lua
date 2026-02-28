function nthPrime(n)
    local count = 0
    local candidate = 2
    while count < n do
        local isPrime = 1
        local divisor = 2
        while divisor * divisor <= candidate do
            if candidate % divisor == 0 then
                isPrime = 0
            end
            divisor = divisor + 1
        end
        if isPrime == 1 then
            count = count + 1
        end
        if count < n then
            candidate = candidate + 1
        end
    end
    return candidate
end

answer = nthPrime(1)
