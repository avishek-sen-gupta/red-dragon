def nth_prime(n):
    count = 0
    candidate = 2
    while count < n:
        is_prime = 1
        divisor = 2
        while divisor * divisor <= candidate:
            if candidate % divisor == 0:
                is_prime = 0
            divisor = divisor + 1
        if is_prime == 1:
            count = count + 1
        if count < n:
            candidate = candidate + 1
    return candidate


answer = nth_prime(1)
