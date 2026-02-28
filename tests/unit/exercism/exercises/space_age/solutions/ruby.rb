def space_age(planet, seconds)
    ratio = 1.0
    if planet == "Mercury"
        ratio = 0.2408467
    end
    if planet == "Venus"
        ratio = 0.61519726
    end
    if planet == "Mars"
        ratio = 1.8808158
    end
    if planet == "Jupiter"
        ratio = 11.862615
    end
    if planet == "Saturn"
        ratio = 29.447498
    end
    if planet == "Uranus"
        ratio = 84.016846
    end
    if planet == "Neptune"
        ratio = 164.79132
    end
    divisor = 31557600.0 * ratio
    return seconds / divisor
end

answer = space_age("Earth", 1000000000)
