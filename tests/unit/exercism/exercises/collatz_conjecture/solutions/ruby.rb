def collatz_steps(number)
    steps = 0
    while number != 1
        if number % 2 == 0
            number = number / 2
        else
            number = number * 3 + 1
        end
        steps = steps + 1
    end
    return steps
end

answer = collatz_steps(16)
