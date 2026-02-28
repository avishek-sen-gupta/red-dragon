def color_code(color)
    if color == "black"
        return 0
    end
    if color == "brown"
        return 1
    end
    if color == "red"
        return 2
    end
    if color == "orange"
        return 3
    end
    if color == "yellow"
        return 4
    end
    if color == "green"
        return 5
    end
    if color == "blue"
        return 6
    end
    if color == "violet"
        return 7
    end
    if color == "grey"
        return 8
    end
    if color == "white"
        return 9
    end
    return -1
end

answer = color_code("black")
