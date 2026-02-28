function spaceAge(planet: string, seconds: number): number {
    let ratio = 1.0;
    if (planet == "Mercury") {
        ratio = 0.2408467;
    }
    if (planet == "Venus") {
        ratio = 0.61519726;
    }
    if (planet == "Mars") {
        ratio = 1.8808158;
    }
    if (planet == "Jupiter") {
        ratio = 11.862615;
    }
    if (planet == "Saturn") {
        ratio = 29.447498;
    }
    if (planet == "Uranus") {
        ratio = 84.016846;
    }
    if (planet == "Neptune") {
        ratio = 164.79132;
    }
    return seconds / (31557600.0 * ratio);
}

let answer: number = spaceAge("Earth", 1000000000);
