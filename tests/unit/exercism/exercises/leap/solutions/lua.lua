function leapYear(year)
    if year % 400 == 0 then
        return 1
    end
    if year % 100 == 0 then
        return 0
    end
    if year % 4 == 0 then
        return 1
    end
    return 0
end

answer = leapYear(2000)
