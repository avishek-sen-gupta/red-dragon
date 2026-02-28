def leap_year(year)
    if year % 400 == 0
        return 1
    end
    if year % 100 == 0
        return 0
    end
    if year % 4 == 0
        return 1
    end
    return 0
end

answer = leap_year(2000)
