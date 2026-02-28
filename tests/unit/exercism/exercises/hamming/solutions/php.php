<?php
function hammingDistance($s1, $s2, $n) {
    $distance = 0;
    $i = 0;
    while ($i < $n) {
        if ($s1[$i] != $s2[$i]) {
            $distance = $distance + 1;
        }
        $i = $i + 1;
    }
    return $distance;
}

$answer = hammingDistance("GAGCCTACTAACGGGAT", "CATCGTAATGACGGCCT", 17);
?>
