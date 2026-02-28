function spaceAge(planet, seconds)
    local ratio = 1.0
    if planet == "Mercury" then
        ratio = 0.2408467
    end
    if planet == "Venus" then
        ratio = 0.61519726
    end
    if planet == "Mars" then
        ratio = 1.8808158
    end
    if planet == "Jupiter" then
        ratio = 11.862615
    end
    if planet == "Saturn" then
        ratio = 29.447498
    end
    if planet == "Uranus" then
        ratio = 84.016846
    end
    if planet == "Neptune" then
        ratio = 164.79132
    end
    return seconds / (31557600.0 * ratio)
end

answer = spaceAge("Earth", 1000000000)
