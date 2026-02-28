function toUpperChar(c) {
    if (c == "a") { return "A"; }
    if (c == "b") { return "B"; }
    if (c == "c") { return "C"; }
    if (c == "d") { return "D"; }
    if (c == "e") { return "E"; }
    if (c == "f") { return "F"; }
    if (c == "g") { return "G"; }
    if (c == "h") { return "H"; }
    if (c == "i") { return "I"; }
    if (c == "j") { return "J"; }
    if (c == "k") { return "K"; }
    if (c == "l") { return "L"; }
    if (c == "m") { return "M"; }
    if (c == "n") { return "N"; }
    if (c == "o") { return "O"; }
    if (c == "p") { return "P"; }
    if (c == "q") { return "Q"; }
    if (c == "r") { return "R"; }
    if (c == "s") { return "S"; }
    if (c == "t") { return "T"; }
    if (c == "u") { return "U"; }
    if (c == "v") { return "V"; }
    if (c == "w") { return "W"; }
    if (c == "x") { return "X"; }
    if (c == "y") { return "Y"; }
    if (c == "z") { return "Z"; }
    return c;
}

function abbreviate(phrase, n) {
    let result = "";
    let atWordStart = 1;
    let i = 0;
    while (i < n) {
        let c = phrase[i];
        if (c == " ") { atWordStart = 1; i = i + 1; continue; }
        if (c == "-") { atWordStart = 1; i = i + 1; continue; }
        if (c == "_") { atWordStart = 1; i = i + 1; continue; }
        if (atWordStart == 1) {
            result = result + toUpperChar(c);
            atWordStart = 0;
        }
        i = i + 1;
    }
    return result;
}

let answer = abbreviate("Portable Network Graphics", 25);
