function collatzSteps(number)
    local steps = 0
    while number ~= 1 do
        if number % 2 == 0 then
            number = number / 2
        else
            number = number * 3 + 1
        end
        steps = steps + 1
    end
    return steps
end

answer = collatzSteps(16)
