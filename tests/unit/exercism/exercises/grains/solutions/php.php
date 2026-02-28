<?php
function square($n) {
    $result = 1;
    $i = 1;
    while ($i < $n) {
        $result = $result * 2;
        $i = $i + 1;
    }
    return $result;
}

function total() {
    $result = 0;
    $power = 1;
    $i = 1;
    while ($i <= 64) {
        $result = $result + $power;
        $power = $power * 2;
        $i = $i + 1;
    }
    return $result;
}

$answer = square(1);
?>
