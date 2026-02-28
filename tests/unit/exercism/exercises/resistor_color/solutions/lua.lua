function colorCode(color)
    if color == "black" then return 0 end
    if color == "brown" then return 1 end
    if color == "red" then return 2 end
    if color == "orange" then return 3 end
    if color == "yellow" then return 4 end
    if color == "green" then return 5 end
    if color == "blue" then return 6 end
    if color == "violet" then return 7 end
    if color == "grey" then return 8 end
    if color == "white" then return 9 end
    return -1
end

answer = colorCode("black")
