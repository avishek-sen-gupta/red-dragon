<?php
function reverseString($s, $n) {
    $result = "";
    $i = $n - 1;
    while ($i >= 0) {
        $result = $result . $s[$i];
        $i = $i - 1;
    }
    return $result;
}

$answer = reverseString("robot", 5);
?>
